# tomasulo_entrega.py
# Simulador didático do algoritmo de Tomasulo (MVP funcional)
# - Suporta: ADD, SUB, MUL, DIV, LW, SW, BEQ
# - Estruturas: ROB, RS, LSB, RAT, checkpoints para especulação 1-bit
# - Interface: Tkinter (Load program, Step, Run, Reset)
# - Visualização de pipeline por instrução: IF / ID / EX / MEM / WB / COMMIT / FLUSSHED
# - Registradores mostram a ÚLTIMA INSTRUÇÃO que ESCREVE neles APÓS WB: ex. R1: ADD_03
# - Log mostra predição/resolução de desvio com PC em forma i_0, i_1, ...
# Requisitos: Python 3.8+ (Tkinter incluído)

import tkinter as tk
from tkinter import ttk, scrolledtext
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
import copy

# --------------------------
# Data structures
# --------------------------
@dataclass
class Instruction:
    pc: int
    text: str
    idx: int = 0           # índice da instrução (1,2,3...) na ordem do programa
    op: str = ""
    rd: Optional[str] = None
    rs: Optional[str] = None
    rt: Optional[str] = None
    imm: Optional[int] = None  # immediate ou alvo (dependendo de BEQ)
    state: str = "NotFetched"
    rob_id: Optional[int] = None
    rs_id: Optional[int] = None
    lsb_id: Optional[int] = None
    speculative: bool = False
    fetch_cycle: Optional[int] = None
    issue_cycle: Optional[int] = None
    exec_start: Optional[int] = None
    exec_end: Optional[int] = None
    wb_cycle: Optional[int] = None
    commit_cycle: Optional[int] = None

@dataclass
class ROBEntry:
    id: int
    busy: bool = False
    instr_pc: Optional[int] = None
    dest: Optional[str] = None
    value: Optional[int] = None
    ready: bool = False
    committed: bool = False
    speculative: bool = False
    instr_text: Optional[str] = None
    type: Optional[str] = None  # REG, STORE, BRANCH
    branch_taken: Optional[bool] = None
    checkpoint_id: Optional[int] = None
    enqueue_seq: Optional[int] = None  # para ordenação FIFO lógica

@dataclass
class ReservationStation:
    id: int
    busy: bool = False
    op: Optional[str] = None
    Vj: Optional[int] = None
    Vk: Optional[int] = None
    Qj: Optional[int] = None
    Qk: Optional[int] = None
    rob_id: Optional[int] = None
    instr_pc: Optional[int] = None
    exec_cycles_left: int = 0

@dataclass
class LSBEntry:
    id: int
    busy: bool = False
    op: Optional[str] = None  # LW ou SW
    address: Optional[int] = None
    Vt: Optional[int] = None
    Qt: Optional[int] = None
    rob_id: Optional[int] = None
    instr_pc: Optional[int] = None
    exec_cycles_left: int = 0
    resolved_address: bool = False

@dataclass
class Checkpoint:
    id: int
    RAT: Dict[str, Optional[int]]
    enqueue_seq_snapshot: int

# --------------------------
# Núcleo do simulador
# --------------------------
class TomasuloSim:
    def __init__(self):
        # configuração fixa
        self.rob_size = 16
        self.rs_count = 8
        self.lsb_size = 8
        self.fetch_width = 1
        self.issue_width = 1
        self.commit_width = 1
        self.register_count = 32

        # estado
        self.program: List[Instruction] = []
        self.pc = 0
        self.memory: Dict[int, int] = {}
        self.register_file: Dict[str, int] = {f"R{i}": 0 for i in range(self.register_count)}
        self.RAT: Dict[str, Optional[int]] = {f"R{i}": None for i in range(self.register_count)}
        self.rob: List[ROBEntry] = [ROBEntry(i) for i in range(self.rob_size)]
        self.rob_enqueue_seq = 0
        self.rs: List[ReservationStation] = [ReservationStation(i) for i in range(self.rs_count)]
        self.lsb: List[LSBEntry] = [LSBEntry(i) for i in range(self.lsb_size)]
        self.cycle = 0

        # latências
        self.latencies = {
            "ADD": 2,
            "SUB": 2,
            "MUL": 4,
            "DIV": 8,
            "LW": 3,
            "SW": 2,
            "BEQ": 1,
            "NOP": 1,
        }

        # preditor 1-bit por PC
        self.predictor: Dict[int, bool] = {}

        # checkpoints para especulação
        self.checkpoints: Dict[int, Checkpoint] = {}
        self.next_checkpoint_id = 1
        self.active_checkpoint_id: Optional[int] = None  # um branch especulativo ativo

        # métricas
        self.committed_count = 0
        self.total_stalls = 0
        self.branch_mispredictions = 0
        self.total_fetch = 0
        self.cumulative_rs_occupancy = 0
        self.cumulative_rob_occupancy = 0
        self.cumulative_lsb_occupancy = 0

        # logs do ciclo (predições, resoluções, etc.)
        self.step_logs: List[str] = []

        # controle
        self.halted = False

    # --------------------------
    # Parser de programa
    # --------------------------
    def parse_program_text(self, text: str):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith('#')]
        self.program = []
        pc = 0
        idx_counter = 1
        for ln in lines:
            instr = Instruction(pc=pc, text=ln)
            instr.idx = idx_counter
            parts = ln.replace(',', ' ').split()
            instr.op = parts[0].upper() if parts else "NOP"
            if instr.op in ("ADD", "SUB", "MUL", "DIV"):
                if len(parts) >= 4:
                    instr.rd, instr.rs, instr.rt = parts[1].upper(), parts[2].upper(), parts[3].upper()
            elif instr.op == "LW":
                if len(parts) >= 3:
                    instr.rt = parts[1].upper()
                    imm_part = parts[2]
                    if '(' in imm_part:
                        imm, reg = imm_part.split('(')
                        reg = reg.replace(')', '').upper()
                        instr.imm = int(imm)
                        instr.rs = reg
                    else:
                        instr.imm = int(imm_part)
            elif instr.op == "SW":
                if len(parts) >= 3:
                    instr.rt = parts[1].upper()
                    imm_part = parts[2]
                    if '(' in imm_part:
                        imm, reg = imm_part.split('(')
                        reg = reg.replace(')', '').upper()
                        instr.imm = int(imm)
                        instr.rs = reg
                    else:
                        instr.imm = int(imm_part)
            elif instr.op == "BEQ":
                if len(parts) >= 4:
                    instr.rs, instr.rt = parts[1].upper(), parts[2].upper()
                    instr.imm = int(parts[3])
            else:
                instr.op = "NOP"
            self.program.append(instr)
            pc += 4
            idx_counter += 1

        # reset dinâmico
        self.pc = 0
        self.total_fetch = 0
        self.halted = False

    # --------------------------
    # Helpers
    # --------------------------
    def rob_occupancy(self) -> int:
        return sum(1 for e in self.rob if e.busy)

    def rs_occupancy(self) -> int:
        return sum(1 for r in self.rs if r.busy)

    def lsb_occupancy(self) -> int:
        return sum(1 for l in self.lsb if l.busy)

    def find_free_rob_index(self) -> Optional[int]:
        for i in range(self.rob_size):
            if not self.rob[i].busy:
                return i
        return None

    def find_free_rs_index(self) -> Optional[int]:
        for r in self.rs:
            if not r.busy:
                return r.id
        return None

    def find_free_lsb_index(self) -> Optional[int]:
        for l in self.lsb:
            if not l.busy:
                return l.id
        return None

    def pc_to_label(self, pc: Optional[int]) -> str:
        """
        Converte PC numérico para rótulo i_0, i_1, ...
        Baseado em pc == instr.pc -> usa instr.idx-1
        """
        if pc is None:
            return "?"
        for ins in self.program:
            if ins.pc == pc:
                return f"i_{ins.idx - 1}"
        return str(pc)

    def get_register_view(self, reg_name: str) -> int:
        tag = self.RAT.get(reg_name)
        if tag is not None and 0 <= tag < self.rob_size:
            ent = self.rob[tag]
            if ent.value is not None:
                if isinstance(ent.value, tuple):
                    return ent.value[1]
                return ent.value
        return self.register_file.get(reg_name, 0)

    def get_register_writer_label(self, reg_name: str) -> str:
        """
        Retorna a *última instrução* que ESCREVE neste registrador, APENAS APÓS WB:
        - Considera apenas instruções com destino == reg_name (registrador final).
        - Destinos:
            * ADD/SUB/MUL/DIV -> rd
            * LW               -> rt
            * SW/BEQ           -> não escrevem em registrador (ignorados)
        - Só conta se state in {"WB", "Committed"} e não Flushed.
        - Formato: OP_XX (ex: ADD_03).
        """
        last_instr: Optional[Instruction] = None
        for ins in self.program:
            if ins.state not in ("WB", "Committed"):
                continue
            if ins.state == "Flushed":
                continue

            dest = None
            if ins.op in ("ADD", "SUB", "MUL", "DIV"):
                dest = ins.rd
            elif ins.op == "LW":
                dest = ins.rt
            # SW, BEQ e outros não têm destino em registrador

            if dest == reg_name:
                last_instr = ins

        if last_instr is not None:
            return f"{last_instr.op}_{last_instr.idx:02d}"
        return "-"

    # --------------------------
    # Pipeline stages
    # --------------------------
    def commit_stage(self):
        committed = 0
        busy_entries = sorted([e for e in self.rob if e.busy], key=lambda x: x.enqueue_seq or 0)

        for ent in busy_entries[: self.commit_width]:
            if not ent.ready:
                break

            pc = ent.instr_pc
            dest_reg = ent.dest

            if ent.type == "REG" and dest_reg:
                if self.RAT.get(dest_reg) == ent.id:
                    self.register_file[dest_reg] = ent.value if ent.value is not None else 0
                    self.RAT[dest_reg] = None

            elif ent.type == "STORE":
                if isinstance(ent.value, tuple):
                    addr, val = ent.value
                    self.memory[addr] = val

            for ins in self.program:
                if ins.pc == pc:
                    ins.state = "Committed"
                    ins.commit_cycle = self.cycle
                    break

            ent.busy = False
            ent.ready = False
            ent.committed = True
            ent.instr_pc = None
            ent.dest = None
            ent.value = None
            ent.instr_text = None
            ent.type = None
            ent.branch_taken = None
            ent.checkpoint_id = None
            ent.enqueue_seq = None

            self.committed_count += 1
            committed += 1

        return committed

    def write_result_stage(self):
        results: List[Tuple[int, str, object]] = []

        # RS -> resultados
        for r in self.rs:
            if r.busy and r.exec_cycles_left == 0 and r.rob_id is not None:
                if r.op == "BEQ":
                    left = r.Vj or 0
                    right = r.Vk or 0
                    taken = (left == right)
                    if 0 <= r.rob_id < self.rob_size:
                        ent = self.rob[r.rob_id]
                        ent.branch_taken = taken
                        ent.ready = True
                    pc = r.instr_pc
                    for ins in self.program:
                        if ins.pc == pc:
                            ins.state = "WB"
                            ins.wb_cycle = self.cycle
                    r.busy = False
                    r.op = None
                    r.Vj = None
                    r.Vk = None
                    r.Qj = None
                    r.Qk = None
                    r.rob_id = None
                    r.instr_pc = None
                    r.exec_cycles_left = 0
                    continue

                val = 0
                if r.op in ("ADD", "SUB", "MUL", "DIV"):
                    a = r.Vj or 0
                    b = r.Vk or 0
                    if r.op == "ADD":
                        val = a + b
                    elif r.op == "SUB":
                        val = a - b
                    elif r.op == "MUL":
                        val = a * b
                    elif r.op == "DIV":
                        val = (a // b) if b != 0 else 0
                else:
                    val = r.Vj or 0

                results.append((r.rob_id, r.op, val))
                pc = r.instr_pc
                r.busy = False
                r.op = None
                r.Vj = None
                r.Vk = None
                r.Qj = None
                r.Qk = None
                r.rob_id = None
                r.instr_pc = None
                r.exec_cycles_left = 0
                for ins in self.program:
                    if ins.pc == pc:
                        ins.state = "WB"
                        ins.wb_cycle = self.cycle

        # LSB -> resultados
        for l in self.lsb:
            if l.busy and l.exec_cycles_left == 0 and l.rob_id is not None:
                if l.op == "LW":
                    val = self.memory.get(l.address, 0)
                    results.append((l.rob_id, "LW", val))
                elif l.op == "SW":
                    results.append((l.rob_id, "SW", (l.address, l.Vt if l.Vt is not None else 0)))
                pc = l.instr_pc
                l.busy = False
                l.op = None
                l.address = None
                l.Vt = None
                l.Qt = None
                l.rob_id = None
                l.instr_pc = None
                l.exec_cycles_left = 0
                l.resolved_address = False
                for ins in self.program:
                    if ins.pc == pc:
                        ins.state = "WB"
                        ins.wb_cycle = self.cycle

        # Broadcast no "CDB"
        for rob_id, op, value in results:
            if 0 <= rob_id < self.rob_size:
                ent = self.rob[rob_id]
                ent.value = value
                ent.ready = True

            for r in self.rs:
                if r.busy:
                    if r.Qj == rob_id:
                        r.Vj = value if not isinstance(value, tuple) else (value[1] if op == "SW" else value)
                        r.Qj = None
                    if r.Qk == rob_id:
                        r.Vk = value if not isinstance(value, tuple) else (value[1] if op == "SW" else value)
                        r.Qk = None

            for l in self.lsb:
                if l.busy:
                    if l.Qt == rob_id:
                        l.Vt = value if not isinstance(value, tuple) else (value[1] if op == "SW" else value)
                        l.Qt = None

    def execute_stage(self):
        for r in self.rs:
            if r.busy and r.exec_cycles_left > 0:
                r.exec_cycles_left -= 1
                for ins in self.program:
                    if ins.pc == r.instr_pc:
                        ins.state = "Executing"
                        if r.exec_cycles_left == 0:
                            ins.exec_end = self.cycle

        for l in self.lsb:
            if l.busy and l.exec_cycles_left > 0:
                l.exec_cycles_left -= 1
                for ins in self.program:
                    if ins.pc == l.instr_pc:
                        ins.state = "Executing"
                        if l.exec_cycles_left == 0:
                            ins.exec_end = self.cycle

    def issue_stage(self):
        issued = 0
        for _ in range(self.issue_width):
            instr = next((i for i in self.program if i.pc == self.pc and i.state == "NotFetched"), None)
            if instr is None:
                if any(i.state == "NotFetched" for i in self.program):
                    self.pc += 4
                    continue
                else:
                    break

            free_rob_idx = self.find_free_rob_index()
            if free_rob_idx is None:
                self.total_stalls += 1
                break

            if instr.op in ("LW", "SW"):
                free_lsb = self.find_free_lsb_index()
                if free_lsb is None:
                    self.total_stalls += 1
                    break
            else:
                free_rs = self.find_free_rs_index()
                if free_rs is None:
                    self.total_stalls += 1
                    break

            # Preenche ROB
            rob_ent = self.rob[free_rob_idx]
            rob_ent.busy = True
            rob_ent.instr_pc = instr.pc
            rob_ent.instr_text = instr.text
            rob_ent.ready = False
            rob_ent.committed = False
            rob_ent.checkpoint_id = None
            rob_ent.enqueue_seq = self.rob_enqueue_seq
            rob_ent.speculative = False
            self.rob_enqueue_seq += 1

            if instr.op in ("ADD", "SUB", "MUL", "DIV", "LW"):
                rob_ent.type = "REG"
                rob_ent.dest = instr.rd if instr.rd else (instr.rt if instr.op == "LW" else None)
            elif instr.op == "SW":
                rob_ent.type = "STORE"
                rob_ent.dest = None
            elif instr.op == "BEQ":
                rob_ent.type = "BRANCH"
                rob_ent.dest = None
            else:
                rob_ent.type = "REG"

            # BEQ: checkpoint, especulação, predição
            if instr.op == "BEQ":
                cp_id = self.next_checkpoint_id
                self.next_checkpoint_id += 1
                self.active_checkpoint_id = cp_id
                cp = Checkpoint(cp_id, copy.deepcopy(self.RAT), self.rob_enqueue_seq)
                self.checkpoints[cp_id] = cp
                rob_ent.checkpoint_id = cp_id
                rob_ent.speculative = True
                instr.speculative = True

                pred = self.predictor.get(instr.pc, False)
                pred_str = "Tomado" if pred else "Não tomado"
                spec_pc = instr.imm if (pred and instr.imm is not None) else instr.pc + 4
                self.step_logs.append(
                    f"[PRED] BEQ '{instr.text}' @ {self.pc_to_label(instr.pc)} | "
                    f"Predição={pred_str} | Próximo PC especulado={self.pc_to_label(spec_pc)}"
                )

                if pred and instr.imm is not None:
                    self.pc = instr.imm
                else:
                    self.pc += 4
            else:
                self.pc += 4
                if self.active_checkpoint_id is not None:
                    rob_ent.speculative = True
                    rob_ent.checkpoint_id = self.active_checkpoint_id
                    instr.speculative = True

            # Load/Store
            if instr.op in ("LW", "SW"):
                l = self.lsb[free_lsb]
                l.busy = True
                l.op = instr.op
                l.instr_pc = instr.pc
                l.rob_id = free_rob_idx

                base = instr.rs
                offset = instr.imm or 0
                if base:
                    rat = self.RAT.get(base)
                    if rat is not None:
                        l.address = self.register_file.get(base, 0) + offset if rat is None else None
                    else:
                        l.address = self.register_file.get(base, 0) + offset

                if instr.op == "SW":
                    src = instr.rt
                    if src:
                        rat_src = self.RAT.get(src)
                        if rat_src is not None:
                            l.Qt = rat_src
                            l.Vt = None
                        else:
                            l.Qt = None
                            l.Vt = self.register_file.get(src, 0)

                if instr.op == "LW":
                    rob_ent.dest = instr.rt
                    self.RAT[instr.rt] = free_rob_idx

                instr.lsb_id = l.id
                instr.rob_id = free_rob_idx
                instr.state = "Issued"
                instr.issue_cycle = self.cycle
                l.exec_cycles_left = self.latencies.get("LW", 3)
                issued += 1

            elif instr.op == "BEQ":
                r = self.rs[free_rs]
                r.busy = True
                r.op = "BEQ"
                r.instr_pc = instr.pc
                r.rob_id = free_rob_idx

                if instr.rs:
                    rat = self.RAT.get(instr.rs)
                    if rat is not None:
                        r.Qj = rat
                    else:
                        r.Vj = self.register_file.get(instr.rs, 0)
                if instr.rt:
                    rat = self.RAT.get(instr.rt)
                    if rat is not None:
                        r.Qk = rat
                    else:
                        r.Vk = self.register_file.get(instr.rt, 0)

                r.exec_cycles_left = self.latencies.get("BEQ", 1)
                instr.rob_id = free_rob_idx
                instr.rs_id = r.id
                instr.state = "Issued"
                instr.issue_cycle = self.cycle
                issued += 1

            else:
                # operações aritméticas
                r = self.rs[free_rs]
                r.busy = True
                r.op = instr.op
                r.instr_pc = instr.pc
                r.rob_id = free_rob_idx

                if instr.rs:
                    rat = self.RAT.get(instr.rs)
                    if rat is not None:
                        r.Qj = rat
                    else:
                        r.Vj = self.register_file.get(instr.rs, 0)
                if instr.rt:
                    rat = self.RAT.get(instr.rt)
                    if rat is not None:
                        r.Qk = rat
                    else:
                        r.Vk = self.register_file.get(instr.rt, 0)

                r.exec_cycles_left = self.latencies.get(instr.op, 2)
                if rob_ent.dest:
                    self.RAT[rob_ent.dest] = free_rob_idx

                instr.rob_id = free_rob_idx
                instr.rs_id = r.id
                instr.state = "Issued"
                instr.issue_cycle = self.cycle
                issued += 1

            self.cumulative_rs_occupancy += self.rs_occupancy()
            self.cumulative_rob_occupancy += self.rob_occupancy()
            self.cumulative_lsb_occupancy += self.lsb_occupancy()
            self.total_fetch += 1

        return issued

    def resolve_branches(self):
        for ent in self.rob:
            if ent.busy and ent.type == "BRANCH" and ent.ready:
                instr_pc = ent.instr_pc
                if instr_pc is None:
                    continue

                predicted = self.predictor.get(instr_pc, False)
                actual = ent.branch_taken if ent.branch_taken is not None else False
                self.predictor[instr_pc] = actual

                pred_str = "Tomado" if predicted else "Não tomado"
                actual_str = "Tomado" if actual else "Não tomado"
                instr = next((i for i in self.program if i.pc == instr_pc), None)
                instr_text = instr.text if instr else "?"

                cp_id = ent.checkpoint_id
                new_pc = None

                if predicted != actual:
                    self.branch_mispredictions += 1

                    for e in self.rob:
                        if e.busy and e.speculative and e != ent:
                            for r in self.rs:
                                if r.busy and r.rob_id == e.id:
                                    r.busy = False
                                    r.op = None
                                    r.Vj = None
                                    r.Vk = None
                                    r.Qj = None
                                    r.Qk = None
                                    r.rob_id = None
                                    r.instr_pc = None
                                    r.exec_cycles_left = 0
                            for l in self.lsb:
                                if l.busy and l.rob_id == e.id:
                                    l.busy = False
                                    l.op = None
                                    l.address = None
                                    l.Vt = None
                                    l.Qt = None
                                    l.rob_id = None
                                    l.instr_pc = None
                                    l.exec_cycles_left = 0

                            e.busy = False
                            e.ready = False
                            e.instr_pc = None
                            e.dest = None
                            e.value = None
                            e.instr_text = None
                            e.type = None
                            e.speculative = False
                            e.enqueue_seq = None

                    if cp_id and cp_id in self.checkpoints:
                        cp = self.checkpoints[cp_id]
                        self.RAT = copy.deepcopy(cp.RAT)

                        target_pc = None
                        for ins in self.program:
                            if ins.pc == instr_pc:
                                target_pc = ins.imm
                                break

                        if actual and target_pc is not None:
                            new_pc = target_pc
                        else:
                            new_pc = instr_pc + 4

                        self.pc = new_pc

                        # TODAS as instruções especulativas viram Flushed
                        for ins in self.program:
                            if ins.speculative:
                                ins.state = "Flushed"
                                ins.speculative = False

                        del self.checkpoints[cp_id]

                    if new_pc is None:
                        new_pc = self.pc

                    self.step_logs.append(
                        f"[RESOLVE] BEQ '{instr_text}' @ {self.pc_to_label(instr_pc)} | "
                        f"Predição={pred_str} | Real={actual_str} | "
                        f"Status=MISPRED | Especulação=Flush, novo PC={self.pc_to_label(new_pc)}"
                    )
                else:
                    ent.speculative = False
                    if cp_id and cp_id in self.checkpoints:
                        del self.checkpoints[cp_id]

                    for e2 in self.rob:
                        if e2.checkpoint_id == cp_id:
                            e2.speculative = False
                    for ins in self.program:
                        if ins.speculative:
                            ins.speculative = False

                    self.step_logs.append(
                        f"[RESOLVE] BEQ '{instr_text}' @ {self.pc_to_label(instr_pc)} | "
                        f"Predição={pred_str} | Real={actual_str} | "
                        f"Status=CORRETA | Especulação mantida"
                    )

                self.active_checkpoint_id = None

    def step(self):
        if self.halted:
            return {}

        self.step_logs = []

        self.cycle += 1
        self.cumulative_rs_occupancy += self.rs_occupancy()
        self.cumulative_rob_occupancy += self.rob_occupancy()
        self.cumulative_lsb_occupancy += self.lsb_occupancy()

        committed = self.commit_stage()
        self.write_result_stage()

        for r in self.rs:
            if (
                r.busy
                and r.op == "BEQ"
                and r.Qj is None
                and r.Qk is None
                and r.rob_id is not None
                and r.exec_cycles_left == 0
            ):
                left = r.Vj or 0
                right = r.Vk or 0
                taken = (left == right)
                ent = self.rob[r.rob_id]
                ent.branch_taken = taken
                ent.ready = True

        self.resolve_branches()
        self.execute_stage()
        issued = self.issue_stage()

        if all((not e.busy) for e in self.rob) and all((not r.busy) for r in self.rs) and all(
            (not l.busy) for l in self.lsb
        ):
            if all(ins.state in ("Committed", "Flushed", "NOP") for ins in self.program):
                self.halted = True

        return {
            "cycle": self.cycle,
            "committed": committed,
            "issued": issued,
            "stalls": self.total_stalls,
            "committed_total": self.committed_count,
            "branch_logs": self.step_logs,
        }

    def reset(self):
        self.__init__()

# --------------------------
# GUI
# --------------------------
class TomasuloApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tomasulo Simulator - Entrega")

        self.sim = TomasuloSim()
        self.running = False
        self.run_delay = 300

        self.create_widgets()
        self.update_views_periodic()

    def get_pipeline_stage_for_instr(self, ins: Instruction) -> str:
        sim = self.sim

        if ins.state == "Committed":
            return "COMMIT"
        if ins.state == "WB":
            return "WB"

        for r in sim.rs:
            if r.busy and r.instr_pc == ins.pc and r.exec_cycles_left > 0:
                return "EX"

        for l in sim.lsb:
            if l.busy and l.instr_pc == ins.pc and l.exec_cycles_left > 0:
                return "MEM"

        if ins.state == "Issued":
            return "ID"

        if ins.state == "NotFetched" and ins.pc == sim.pc:
            return "IF"

        if ins.state == "Flushed":
            return "FLUSSHED"

        return ""

    def create_widgets(self):
        top = ttk.Frame(self.root, padding=6)
        top.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(top)
        left.grid(row=0, column=0, sticky="nsew")
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Programa MIPS:").grid(row=0, column=0, sticky="w")
        self.prog_text = scrolledtext.ScrolledText(left, width=40, height=20)
        self.prog_text.grid(row=1, column=0, sticky="nsew")

        sample = """# Exemplo 1: dependência simples
ADD R1, R2, R3
ADD R4, R1, R5
MUL R6, R7, R8
# Exemplo 2: load/store
SW R2, 0(R3)
LW R1, 0(R3)
# Exemplo 3: branch
ADD R1, R0, R0
BEQ R1, R0, 28
ADD R2, R3, R4
"""
        self.prog_text.insert("1.0", sample)

        ctrl_frame = ttk.Frame(left)
        ctrl_frame.grid(row=2, column=0, sticky="we", pady=6)

        ttk.Button(ctrl_frame, text="Carregar programa", command=self.load_program).grid(row=0, column=0)
        ttk.Button(ctrl_frame, text="Step (1 ciclo)", command=self.step).grid(row=0, column=1)
        self.run_btn = ttk.Button(ctrl_frame, text="Run", command=self.toggle_run)
        self.run_btn.grid(row=0, column=2)
        ttk.Button(ctrl_frame, text="Reset", command=self.reset).grid(row=0, column=3)

        right = ttk.Frame(top)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        ttk.Label(right, text="Instruções / Pipeline").grid(row=1, column=0, sticky="w")
        self.instr_table = ttk.Treeview(
            right,
            columns=("pc", "idx", "text", "stage", "state", "rob"),
            show="headings",
            height=8,
        )
        for c, title in zip(
            ("pc", "idx", "text", "stage", "state", "rob"),
            ("PC", "#", "Instrução", "STAGE", "STATE", "ROB"),
        ):
            self.instr_table.heading(c, text=title)
        self.instr_table.column("pc", width=70, anchor="center")
        self.instr_table.column("idx", width=40, anchor="center")
        self.instr_table.column("stage", width=80, anchor="center")
        self.instr_table.column("state", width=80, anchor="center")
        self.instr_table.column("rob", width=50, anchor="center")
        self.instr_table.grid(row=2, column=0, sticky="nsew")

        self.instr_table.tag_configure("IF", background="#e3f2fd")
        self.instr_table.tag_configure("ID", background="#e8f5e9")
        self.instr_table.tag_configure("EX", background="#fff3e0")
        self.instr_table.tag_configure("MEM", background="#f3e5f5")
        self.instr_table.tag_configure("WB", background="#ffebee")
        self.instr_table.tag_configure("COMMIT", background="#e0f7fa")
        self.instr_table.tag_configure("FLUSSHED", background="#eeeeee")

        ttk.Label(right, text="ROB").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.rob_table = ttk.Treeview(
            right,
            columns=("id", "busy", "type", "dest", "ready", "spec", "instr"),
            show="headings",
            height=5,
        )
        for c in ("id", "busy", "type", "dest", "ready", "spec", "instr"):
            self.rob_table.heading(c, text=c.upper())
        self.rob_table.grid(row=4, column=0, sticky="nsew")

        ttk.Label(right, text="RS").grid(row=5, column=0, sticky="w", pady=(6, 0))
        self.rs_table = ttk.Treeview(
            right,
            columns=("id", "busy", "op", "Vj", "Vk", "Qj", "Qk", "rob"),
            show="headings",
            height=5,
        )
        for c in ("id", "busy", "op", "Vj", "Vk", "Qj", "Qk", "rob"):
            self.rs_table.heading(c, text=c.upper())
        self.rs_table.grid(row=6, column=0, sticky="nsew")

        ttk.Label(right, text="LSB").grid(row=7, column=0, sticky="w", pady=(6, 0))
        self.lsb_table = ttk.Treeview(
            right,
            columns=("id", "busy", "op", "addr", "Vt", "Qt", "rob"),
            show="headings",
            height=5,
        )
        for c in ("id", "busy", "op", "addr", "Vt", "Qt", "rob"):
            self.lsb_table.heading(c, text=c.upper())
        self.lsb_table.grid(row=8, column=0, sticky="nsew")

        bottom = ttk.Frame(self.root, padding=6)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew")
        bottom.columnconfigure(1, weight=1)

        ttk.Label(
            bottom,
            text="Registradores:",
        ).grid(row=0, column=0, sticky="w")
        self.reg_text = tk.Text(bottom, height=4, width=100)
        self.reg_text.grid(row=1, column=0, columnspan=3, sticky="we")

        ttk.Label(bottom, text="Logs:").grid(
            row=2, column=0, sticky="w"
        )
        self.log_text = scrolledtext.ScrolledText(bottom, height=6)
        self.log_text.grid(row=3, column=0, columnspan=3, sticky="we")

        self.metrics_lbl = ttk.Label(
            bottom,
            text="Ciclo: 0 | Instruções: 0 | Committed: 0 | IPC: 0.00 | Stalls: 0 | Mispred: 0",
        )
        self.metrics_lbl.grid(row=4, column=0, sticky="w")

    def log(self, s: str):
        self.log_text.insert("end", f"[C{self.sim.cycle}] {s}\n")
        self.log_text.see("end")

    def load_program(self):
        txt = self.prog_text.get("1.0", "end").strip()
        if not txt:
            self.log("Nenhum programa para carregar.")
            return

        self.sim = TomasuloSim()
        self.sim.parse_program_text(txt)
        self.sim.cycle = 0
        self.sim.committed_count = 0
        self.sim.total_stalls = 0
        self.sim.branch_mispredictions = 0
        self.sim.rob_enqueue_seq = 0
        self.sim.halted = False

        self.log_text.delete("1.0", "end")
        self.log("Programa carregado")
        self.update_views()

    def update_views(self):
        # Instruções / pipeline
        for i in self.instr_table.get_children():
            self.instr_table.delete(i)
        for ins in self.sim.program:
            rob = str(ins.rob_id) if ins.rob_id is not None else ""
            stage = self.get_pipeline_stage_for_instr(ins)
            tags = (stage,) if stage else ()
            pc_label = self.sim.pc_to_label(ins.pc)
            self.instr_table.insert(
                "",
                "end",
                values=(pc_label, ins.idx, ins.text, stage, ins.state, rob),
                tags=tags,
            )

        # ROB
        for i in self.rob_table.get_children():
            self.rob_table.delete(i)
        for e in self.sim.rob:
            self.rob_table.insert(
                "",
                "end",
                values=(
                    e.id,
                    str(e.busy),
                    e.type or "",
                    e.dest or "",
                    str(e.ready),
                    str(e.speculative),
                    e.instr_text or "",
                ),
            )

        # RS
        for i in self.rs_table.get_children():
            self.rs_table.delete(i)
        for r in self.sim.rs:
            self.rs_table.insert(
                "",
                "end",
                values=(
                    r.id,
                    str(r.busy),
                    r.op or "",
                    str(r.Vj) if r.Vj is not None else "",
                    str(r.Vk) if r.Vk is not None else "",
                    str(r.Qj) if r.Qj is not None else "",
                    str(r.Qk) if r.Qk is not None else "",
                    str(r.rob_id) if r.rob_id is not None else "",
                ),
            )

        # LSB
        for i in self.lsb_table.get_children():
            self.lsb_table.delete(i)
        for l in self.sim.lsb:
            self.lsb_table.insert(
                "",
                "end",
                values=(
                    l.id,
                    str(l.busy),
                    l.op or "",
                    str(l.address) if l.address is not None else "",
                    str(l.Vt) if l.Vt is not None else "",
                    str(l.Qt) if l.Qt is not None else "",
                    str(l.rob_id) if l.rob_id is not None else "",
                ),
            )

        # Registradores
        self.reg_text.delete("1.0", "end")
        regs_lines = []
        for i in range(0, self.sim.register_count, 8):
            chunk = []
            for j in range(i, i + 8):
                reg_name = f"R{j}"
                label = self.sim.get_register_writer_label(reg_name)
                chunk.append(f"{reg_name}: {label}")
            regs_lines.append(" | ".join(chunk))
        self.reg_text.insert("1.0", "\n".join(regs_lines))

        # Métricas
        cycles = self.sim.cycle
        committed = self.sim.committed_count
        ipc = (committed / cycles) if cycles > 0 else 0.0
        total_instr = len(self.sim.program)
        self.metrics_lbl.config(
            text=(
                f"Ciclo: {cycles} | Instruções: {total_instr} | "
                f"Committed: {committed} | IPC: {ipc:.2f} | "
                f"Stalls (bolhas): {self.sim.total_stalls} | "
                f"Mispred: {self.sim.branch_mispredictions}"
            )
        )

    def step(self):
        if not self.sim.program:
            self.log("Nenhum programa carregado.")
            return

        res = self.sim.step()

        if res.get("committed", 0) > 0:
            self.log(f"Committed {res['committed']} instr(s)")
        if res.get("issued", 0) > 0:
            self.log(f"Issued {res['issued']} instr(s)")

        for msg in res.get("branch_logs", []):
            self.log(msg)

        self.update_views()

        if self.sim.halted:
            self.log("Simulação finalizada")
            self.running = False
            self.run_btn.config(text="Run")

    def run_loop(self):
        if not self.running:
            return
        self.step()
        if self.running:
            self.root.after(int(self.run_delay), self.run_loop)

    def toggle_run(self):
        if not self.sim.program:
            self.log("Nenhum programa carregado.")
            return
        self.running = not self.running
        if self.running:
            self.run_btn.config(text="Pause")
            self.run_loop()
        else:
            self.run_btn.config(text="Run")



    def reset(self):
        txt = self.prog_text.get("1.0", "end").strip()
        self.sim = TomasuloSim()
        if txt:
            self.sim.parse_program_text(txt)
        self.log_text.delete("1.0", "end")
        self.log("Simulador resetado")
        self.update_views()

    def update_views_periodic(self):
        self.update_views()
        self.root.after(500, self.update_views_periodic)

# --------------------------
# Run
# --------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1080x820")
    app = TomasuloApp(root)
    root.mainloop()
