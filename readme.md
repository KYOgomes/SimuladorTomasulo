
# Simulador Tomasulo

## Descrição

O Simulador Tomasulo é uma ferramenta educacional que implementa o algoritmo de execução fora de ordem de Tomasulo, utilizado em processadores modernos para melhorar o desempenho através do paralelismo de instruções.

## Principais Funções

### 1. **Despacho de Instruções**
- Carrega instruções do buffer de instruções
- Verifica disponibilidade de estações de reserva
- Aloca recursos necessários

### 2. **Estações de Reserva**
- Armazena operandos e operações pendentes
- Gerencia dependências de dados
- Implementa renomeação de registradores

### 3. **Execução Fora de Ordem**
- Executa instruções assim que operandos estão disponíveis
- Permite paralelismo independente de ordem original
- Contorna hazards de dados

### 4. **Barramento de Resultado (CDB)**
- Transmite resultados para registradores e estações
- Resolve dependências através de broadcasts
- Atualiza estado da máquina

### 5. **Gerenciamento de Registradores**
- Renomeação para eliminar anti-dependências
- Controle de buffer de retirada de instruções
- Serialização de commits

## Estrutura do Projeto

```
SimuladorTomasulo/
├── core/          # Núcleo do algoritmo
├── models/        # Estruturas de dados
├── execution/     # Motor de execução
└── ui/           # Interface
```
