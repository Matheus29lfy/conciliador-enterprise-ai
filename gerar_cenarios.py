import pandas as pd
import os
from datetime import datetime, timedelta

# Configuração
data_base = datetime(2025, 1, 10)
os.makedirs('data/input', exist_ok=True)

# --- 1. DADOS DO PROTHEUS ---
dados_protheus = [
    # Cenário 1: Match Perfeito
    {'Data': data_base, 'Historico': 'PGTO FORNECEDOR ALPHA', 'Valor': 1500.00, 'Natureza': 'D'},
    # Cenário 2: Tolerância Matemática (1 dia de dif)
    {'Data': data_base, 'Historico': 'PGTO BOLETO SERVICOS', 'Valor': 345.50, 'Natureza': 'D'},
    # Cenário 3: Match Perfeito Recebimento
    {'Data': data_base + timedelta(days=2), 'Historico': 'RECEB. CLIENTE BETA', 'Valor': 5000.00, 'Natureza': 'C'},
    # Cenário 4: Erro no Protheus
    {'Data': data_base + timedelta(days=5), 'Historico': 'PGTO MANUTENCAO PENDENTE', 'Valor': 200.00, 'Natureza': 'D'},
    
    # 🔥 CENÁRIO 6: O TESTE DA IA (Mesmo valor, data 4 dias longe)
    {'Data': data_base, 'Historico': 'CONSULTORIA DE TI SPECIAL', 'Valor': 1250.00, 'Natureza': 'D'},
]

# --- 2. DADOS DO BANCO ---
dados_banco = [
    # Match Perfeito
    {'Data': data_base, 'Descricao': 'DOC ELET FORN ALPHA', 'Valor': -1500.00},
    # Tolerância Matemática
    {'Data': data_base + timedelta(days=1), 'Descricao': 'COBRANCA BANCARIA', 'Valor': -345.50},
    # Match Perfeito Recebimento
    {'Data': data_base + timedelta(days=2), 'Descricao': 'CREDITO TED CLIENTE BETA', 'Valor': 5000.00},
    # Cenário 5: Tarifa Bancária
    {'Data': data_base + timedelta(days=3), 'Descricao': 'TARIFA CESTA SERVICOS', 'Valor': -55.90},
    
    # 🔥 CENÁRIO 6: O TESTE DA IA (Descrição diferente, Data D+4)
    # A matemática só pega até D+3. A IA pega até D+5.
    {'Data': data_base + timedelta(days=4), 'Descricao': 'DEBITO PAGAMENTO SERVICO EXT', 'Valor': -1250.00},
]

df_protheus = pd.DataFrame(dados_protheus)
df_banco = pd.DataFrame(dados_banco)

print("Gerando arquivos de cenário...")
df_protheus.to_excel('data/input/sistema_protheus.xlsx', index=False)
df_banco.to_excel('data/input/extrato_banco.xlsx', index=False)
print("✅ Arquivos atualizados com Cenário de IA!")