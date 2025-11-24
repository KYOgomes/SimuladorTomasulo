# Simulador Tomasulo - Execução Fora de Ordem

## 📖 Descrição

Simulador didático do **Algoritmo de Tomasulo** com interface gráfica, implementando execução fora de ordem (out-of-order execution) com especulação de desvios e predição de branches. Ferramenta educacional para visualização e compreensão de arquiteturas de processadores superescalares.

## ✨ Características Principais

### Instruções Suportadas
- **Aritméticas**: `ADD`, `SUB`, `MUL`, `DIV`
- **Memória**: `LW` (Load Word), `SW` (Store Word)
- **Controle**: `BEQ` (Branch on Equal)

### Estruturas Implementadas
- **ROB** (Reorder Buffer): 16 entradas - garante commit em ordem
- **RS** (Reservation Stations): 8 estações - execução fora de ordem
- **LSB** (Load/Store Buffer): 8 entradas - operações de memória
- **RAT** (Register Alias Table): renomeação de registradores
- **Checkpoints**: para especulação de branches com preditor 1-bit

### Funcionalidades
✅ Execução especulativa de branches  
✅ Predição de desvios (1-bit predictor)  
✅ Flush de instruções especulativas em misprediction  
✅ Visualização ciclo a ciclo do pipeline  
✅ Métricas de desempenho em tempo real  
✅ Interface gráfica intuitiva com Tkinter  

## 🎮 Como Rodar

### Requisitos
- **Python 3.8+** (Tkinter incluído na instalação padrão)
- Sistema Operacional: Windows, Linux ou macOS

### Executar o Simulador

```bash
python tomasulo_entrega.py
```

A interface gráfica será aberta automaticamente.

## 📚 Como Usar

### 1. Carregar um Programa

Ao abrir o simulador, você verá um programa de exemplo pré-carregado:

```assembly
BEQ R1, R2, 12 
LW F6, 0(R1) 
LW F2, 4(R2) 
MUL F0, F2, F4 
SUB F8, F6, F0 
DIV F10, F8, F2 
ADD F4, F10, F6 
SW F4, 8(R3) 
ADD R1, R1, R1 
BEQ R1, R0, 0
```

**Para carregar seu próprio programa:**
1. Digite ou cole as instruções MIPS na caixa de texto à esquerda
2. Clique no botão **"Carregar programa"**

### 2. Executar a Simulação

Você tem três modos de execução:

#### **Step (1 ciclo)**
- Executa **um único ciclo** de relógio
- Ideal para acompanhar passo a passo o que acontece em cada ciclo
- Use para entender detalhadamente o comportamento do algoritmo

#### **Run**
- Executa continuamente até o programa terminar
- Útil para ver o resultado final rapidamente
- Clique em **"Pause"** para interromper

#### **Reset**
- Reinicia o simulador mantendo o programa carregado
- Zera todas as estruturas e métricas
- Use para executar o mesmo programa novamente

### 3. Entendendo a Interface

A interface está dividida em várias seções que mostram o estado completo do simulador:

#### 📊 **Métricas (Topo da tela)**
```
Ciclo: 18 | Instruções: 10 | Committed: 8 | IPC: 0.44 | Stalls (bolhas): 8 | Mispred: 1
```

- **Ciclo**: Número atual do ciclo de relógio
- **Instruções**: Total de instruções no programa
- **Committed**: Instruções já commitadas (finalizadas)
- **IPC** (Instructions Per Cycle): Eficiência do processador
- **Stalls (bolhas)**: Ciclos onde nenhuma instrução foi emitida
- **Mispred**: Número de predições de branch incorretas

#### 📋 **Tabela de Instruções / Pipeline**

Mostra o estado de cada instrução no pipeline:

| Coluna | Descrição |
|--------|-----------|
| **PC** | Program Counter (i_0, i_1, ...) |
| **Idx** | Índice da instrução no programa |
| **Instrução** | Texto da instrução MIPS |
| **Stage** | Estágio atual no pipeline |
| **State** | Estado da instrução |
| **ROB** | ID da entrada no ROB |

**Estágios do Pipeline:**
- **IF** (Instruction Fetch): Buscando instrução
- **ID** (Instruction Decode): Decodificada e na Reservation Station
- **EX** (Execute): Executando operação aritmética
- **MEM** (Memory): Acessando memória (LW/SW)
- **WB** (Write Back): Resultado escrito no ROB
- **COMMIT** (Committed): Instrução commitada (finalizada)
- **FLUSSHED**: Instrução descartada por misprediction

#### 🔄 **ROB (Reorder Buffer)**

Garante que instruções sejam commitadas **em ordem**, mesmo executando fora de ordem:

| Coluna | Descrição |
|--------|-----------|
| **ID** | Identificador da entrada (0-15) |
| **Busy** | Se a entrada está ocupada |
| **Type** | REG (registrador), STORE (memória), BRANCH (desvio) |
| **Dest** | Registrador destino |
| **Ready** | Se o resultado está pronto |
| **Spec** | Se é especulativa (após branch não resolvido) |
| **Instrução** | Texto da instrução |

#### ⚙️ **RS (Reservation Stations)**

Armazena instruções esperando por operandos:

| Coluna | Descrição |
|--------|-----------|
| **ID** | Identificador (0-7) |
| **Busy** | Se está ocupada |
| **Op** | Operação (ADD, SUB, MUL, DIV, BEQ) |
| **Vj/Vk** | Valores dos operandos (quando disponíveis) |
| **Qj/Qk** | ROB ID aguardando (quando operando não está pronto) |
| **ROB** | ID no ROB desta instrução |

**Exemplo:**
- `Vj=5, Vk=3` → Ambos operandos prontos, pode executar
- `Vj=5, Qk=3` → Aguardando ROB[3] completar para obter segundo operando

#### 💾 **LSB (Load/Store Buffer)**

Gerencia operações de memória (LW/SW):

| Coluna | Descrição |
|--------|-----------|
| **ID** | Identificador (0-7) |
| **Busy** | Se está ocupado |
| **Op** | LW ou SW |
| **Addr** | Endereço de memória |
| **Vt/Qt** | Valor/Tag do dado a armazenar (SW) |
| **ROB** | ID no ROB |

#### 📝 **Registradores**

Mostra os 32 registradores do processador:

```
R0: -  R1: ADD_09  R2: -  R3: -  ...
```

- **Formato**: `R{número}: {OPERAÇÃO}_{índice}`
- **Exemplo**: `R1: ADD_09` → R1 foi escrito pela instrução ADD #9
- **"-"**: Registrador não foi modificado ainda

#### 📜 **Log de Eventos**

Mostra eventos importantes como:
```
[PRED] BEQ 'BEQ R1, R2, 12' @ i_0 | Predição=Não tomado | Próximo PC especulado=i_1
[RESOLVE] BEQ 'BEQ R1, R2, 12' @ i_0 | Predição=Não tomado | Real=Tomado | Status=MISPRED | Especulação=Flush, novo PC=i_3
Committed 1 instr(s)
Issued 1 instr(s)
```

## 🔧 Latências Configuradas

As latências (em ciclos) de cada operação são:

| Operação | Ciclos |
|----------|--------|
| ADD | 2 |
| SUB | 2 |
| MUL | 4 |
| DIV | 6 |
| LW | 3 |
| SW | 2 |
| BEQ | 1 |

## 📐 Sintaxe das Instruções

### Instruções Aritméticas
```assembly
ADD Rd, Rs, Rt    # Rd = Rs + Rt
SUB Rd, Rs, Rt    # Rd = Rs - Rt
MUL Rd, Rs, Rt    # Rd = Rs × Rt
DIV Rd, Rs, Rt    # Rd = Rs ÷ Rt
```

### Instruções de Memória
```assembly
LW Rt, offset(Rs)     # Rt = Mem[Rs + offset]
SW Rt, offset(Rs)     # Mem[Rs + offset] = Rt
```

**Exemplo:**
```assembly
LW F6, 0(R1)     # F6 = Memória[R1 + 0]
SW F4, 8(R3)     # Memória[R3 + 8] = F4
```

### Instruções de Desvio
```assembly
BEQ Rs, Rt, target    # Se Rs == Rt, vai para PC=target
```

**Exemplo:**
```assembly
BEQ R1, R2, 12    # Se R1 == R2, pula para PC=12 (instrução i_3)
```

## 🎯 Exemplo de Uso Passo a Passo

1. **Inicie o simulador**: Execute `python tomasulo_entrega.py`

2. **Observe o programa padrão** ou edite conforme necessário

3. **Clique em "Carregar programa"** para inicializar

4. **Clique em "Step (1 ciclo)"** repetidamente e observe:
   - Ciclo 1: Primeira instrução (BEQ) é buscada (IF)
   - Ciclo 2: BEQ vai para ID (entra na RS), predição é feita
   - Instruções especulativas são marcadas
   - Quando BEQ resolve, pode haver MISPRED e flush
   - Instruções executam fora de ordem conforme operandos ficam prontos
   - Commits acontecem **em ordem** através do ROB

5. **Analise as métricas finais** quando o programa terminar

## 🧪 Validação do Simulador

O simulador foi validado com o programa de exemplo, apresentando os seguintes resultados:

```
✓ PASS - Ciclos: 18
✓ PASS - IPC: 0.44
✓ PASS - Stalls (bolhas): 8
```

## 📚 Conceitos Importantes

### Execução Fora de Ordem
Instruções podem ser executadas antes de instruções anteriores se seus operandos estiverem disponíveis, melhorando o paralelismo.

### Renomeação de Registradores
O RAT (Register Alias Table) elimina dependências falsas (WAR e WAW) mapeando registradores lógicos para entradas do ROB.

### Especulação de Branches
Instruções após um branch são executadas especulativamente. Se a predição estiver errada, essas instruções são descartadas (flushed).

### Reorder Buffer (ROB)
Garante que o estado arquitetural seja atualizado na ordem correta do programa, mesmo com execução fora de ordem.

## 👨‍💻 Estrutura do Código

```
tomasulo_entrega.py
├── Data Structures
│   ├── Instruction
│   ├── ROBEntry
│   ├── ReservationStation
│   ├── LSBEntry
│   └── Checkpoint
├── TomasuloSim (Core)
│   ├── commit_stage()
│   ├── write_result_stage()
│   ├── execute_stage()
│   ├── issue_stage()
│   └── resolve_branches()
└── TomasuloApp (GUI)
    └── Interface Tkinter
```

## 📄 Licença

Projeto educacional desenvolvido para a disciplina de Arquitetura de Computadores III - PUC.

## 🤝 Contribuições

Para reportar bugs ou sugerir melhorias, entre em contato com o desenvolvedor.

---

**Desenvolvido com 💻 para fins educacionais**
