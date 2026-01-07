import pandas as pd
import time
import logging
import os
from typing import Tuple, Optional
from datetime import datetime

# --- IMPORTAÇÃO DO AGENTE BLINDADO ---
from agente_seguro_v2 import consultar_agente_blindado

# --- CONFIGURAÇÃO ---
PASTA_INPUT = 'data/input'
PASTA_OUTPUT = 'data/output'
PASTA_LOGS = 'logs'

# Garante estrutura
os.makedirs(PASTA_INPUT, exist_ok=True)
os.makedirs(PASTA_OUTPUT, exist_ok=True)
os.makedirs(PASTA_LOGS, exist_ok=True)

# Regras de Negócio
TOLERANCIA_DIAS = 3
CONFIANCA_MINIMA = ['alta'] 
COLUNAS_PROTHEUS = ['Data', 'Historico', 'Valor', 'Natureza']
COLUNAS_BANCO = ['Data', 'Descricao', 'Valor']
LIMITE_VALOR_MAXIMO = 1_000_000_000.00 

# --- FUNÇÃO DE LOG (CORREÇÃO DO BUG 0KB) ---
def configurar_logger_dinamico():
    """
    Cria um arquivo de log EXCLUSIVO para esta execução, 
    usando timestamp no nome para garantir histórico único.
    """
    logger = logging.getLogger()
    
    # 1. Limpa handlers antigos (limpeza da memória)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # 2. Gera nome único: "log_execucao_2025-01-07_15-30-00.txt"
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    nome_arquivo = f"log_execucao_{timestamp}.txt"
    caminho_log = os.path.join(PASTA_LOGS, nome_arquivo)

    # 3. Configura o FileHandler para este arquivo novo
    file_handler = logging.FileHandler(caminho_log, mode='w', encoding='utf-8') 
    file_handler.setFormatter(formatter)
    
    # 4. Mantém o StreamHandler (para ver no terminal do VS Code também)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    
    # Retorna o logger e o caminho do arquivo (caso queira mostrar na tela qual foi gerado)
    return logger, caminho_log

# Inicializa logger globalmente para funções auxiliares, mas será resetado no pipeline
logger = logging.getLogger()

def validar_schema(df: pd.DataFrame, colunas_esperadas: list, nome_arq: str) -> bool:
    faltantes = [c for c in colunas_esperadas if c not in df.columns]
    if faltantes:
        logger.critical(f"Arquivo {nome_arq} inválido! Faltam colunas: {faltantes}")
        return False
    return True

def validar_regras_negocio(df: pd.DataFrame, origem: str) -> pd.DataFrame:
    # 1. Validação de Intervalo
    outliers = df[(df['Valor_Real'] == 0) | (df['Valor_Real'].abs() > LIMITE_VALOR_MAXIMO)]
    if not outliers.empty:
        logger.warning(f"[{origem}] {len(outliers)} linhas removidas por valores suspeitos.")
        df = df.drop(outliers.index)

    # 2. Detecção de Duplicatas
    cols_dup = ['Data', 'Valor_Real', 'Historico'] if origem == 'Protheus' else ['Data', 'Valor_Real', 'Descricao']
    duplicatas = df[df.duplicated(subset=cols_dup, keep=False)]
    if not duplicatas.empty:
        logger.warning(f"[{origem}] ATENÇÃO: {len(duplicatas)} lançamentos duplicados detectados!")
    
    return df

def carregar_e_saneamento() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    logger.info("📂 Iniciando carregamento e validação de arquivos...") # Agora usa o logger configurado
    try:
        caminho_p = os.path.join(PASTA_INPUT, 'sistema_protheus.xlsx')
        caminho_b = os.path.join(PASTA_INPUT, 'extrato_banco.xlsx')

        if not os.path.exists(caminho_p) or not os.path.exists(caminho_b):
            raise FileNotFoundError

        df_p = pd.read_excel(caminho_p)
        df_b = pd.read_excel(caminho_b)

        if not validar_schema(df_p, COLUNAS_PROTHEUS, "Protheus") or \
           not validar_schema(df_b, COLUNAS_BANCO, "Banco"):
            return None, None

        cols_p_check = ['Valor', 'Historico']
        cols_b_check = ['Valor', 'Descricao']
        
        if df_p[cols_p_check].isnull().any().any() or df_b[cols_b_check].isnull().any().any():
            logger.warning("Linhas com Valor ou Histórico NULOS foram removidas.")
            df_p.dropna(subset=cols_p_check, inplace=True)
            df_b.dropna(subset=cols_b_check, inplace=True)

        df_p['Valor_Real'] = df_p.apply(lambda x: x['Valor'] * -1 if x['Natureza'] == 'D' else x['Valor'], axis=1)
        df_b['Valor_Real'] = df_b['Valor']

        df_p['Valor_Real'] = df_p['Valor_Real'].astype(float).round(2)
        df_b['Valor_Real'] = df_b['Valor_Real'].astype(float).round(2)
        
        df_p['Data'] = pd.to_datetime(df_p['Data'], errors='coerce')
        df_b['Data'] = pd.to_datetime(df_b['Data'], errors='coerce')

        df_p.dropna(subset=['Data'], inplace=True)
        df_b.dropna(subset=['Data'], inplace=True)

        # Ref Auditoria
        df_p['Ref. Auditoria'] = df_p.index.astype(str) + "_PROTHEUS"
        df_b['Ref. Auditoria'] = df_b.index.astype(str) + "_BANCO"

        df_p = validar_regras_negocio(df_p, "Protheus")
        df_b = validar_regras_negocio(df_b, "Banco")

        return df_p, df_b

    except FileNotFoundError:
        logger.error(f"Arquivos não encontrados em '{PASTA_INPUT}'.")
        return None, None
    except Exception as e:
        logger.error(f"ERRO DESCONHECIDO NO CARREGAMENTO: {e}")
        return None, None

def pipeline_enterprise():
    # Pega o logger e o nome do arquivo gerado
    global logger
    logger, caminho_log_atual = configurar_logger_dinamico()
    
    logger.info(f">>> INICIANDO NOVA EXECUÇÃO (ID: {caminho_log_atual}) <<<")
    
    df_p, df_b = carregar_e_saneamento()
    if df_p is None: 
        logger.error("Falha no carregamento. Abortando pipeline.")
        return

    logger.info("⚡ ETAPA 1: Executando Match Exato (Matemático)...")
    print("\n⚡ ETAPA 1: MATCH EXATO (Matemático)...")
    
    match_exato = pd.merge(
        df_p, df_b, 
        on=['Data', 'Valor_Real'], 
        how='outer', indicator=True, suffixes=('_Protheus', '_Banco')
    )
    
    conciliados = match_exato[match_exato['_merge'] == 'both'].copy()
    conciliados['Metodo'] = 'Exato'
    conciliados['Justificativa_Auditoria'] = 'Valores e Datas coincidem perfeitamente.'
    
    pendencias = match_exato[match_exato['_merge'] != 'both']
    
    sobra_p = pendencias[pendencias['_merge'] == 'left_only'][['Data', 'Historico', 'Valor_Real', 'Ref. Auditoria_Protheus']].rename(columns={'Ref. Auditoria_Protheus': 'Ref. Auditoria'})
    sobra_b = pendencias[pendencias['_merge'] == 'right_only'][['Data', 'Descricao', 'Valor_Real', 'Ref. Auditoria_Banco']].rename(columns={'Ref. Auditoria_Banco': 'Ref. Auditoria'})

    logger.info(f"Conciliados Exatos: {len(conciliados)}")
    print(f"   -> {len(conciliados)} conciliados exatos.")

    logger.info("⚡ ETAPA 2: Executando Match Inteligente (Fuzzy + IA)...")
    print("\n⚡ ETAPA 2: MATCH INTELIGENTE (Otimizado + IA)...")
    
    novos_matches = []
    ids_p_removidos = set()
    ids_b_removidos = set()
    
    grupo_banco = sobra_b.groupby('Valor_Real')

    for idx_p, row_p in sobra_p.iterrows():
        val = row_p['Valor_Real']
        
        if val in grupo_banco.groups:
            candidatos_b = grupo_banco.get_group(val)
            
            for idx_b, row_b in candidatos_b.iterrows():
                if row_b['Ref. Auditoria'] in ids_b_removidos: continue
                
                dias_dif = abs((row_p['Data'] - row_b['Data']).days)
                match_found = False
                metodo = ""
                justificativa = ""

                if dias_dif <= TOLERANCIA_DIAS:
                    match_found = True
                    metodo = "Tolerancia Data"
                    justificativa = f"Valor igual, compensado com {dias_dif} dias de diferença."
                    logger.info(f"Match Fuzzy: {row_p['Ref. Auditoria']} <-> {row_b['Ref. Auditoria']} (Dias: {dias_dif})")
                
                elif dias_dif <= 5: 
                    print(f"   🤖 IA Analisando: '{row_p['Historico']}' vs '{row_b['Descricao']}'")
                    logger.info(f"Acionando IA para: '{row_p['Historico']}' vs '{row_b['Descricao']}'")
                    try:
                        res_ia = consultar_agente_blindado(row_p['Historico'], row_b['Descricao'])
                        if res_ia and res_ia['match'] and res_ia['confianca'].lower() in CONFIANCA_MINIMA:
                            match_found = True
                            metodo = "Inteligência Artificial"
                            justificativa = f"[IA Conf: {res_ia['confianca']}] {res_ia['justificativa']}"
                            logger.info(f"IA MATCH CONFIRMADO: {justificativa}")
                        else:
                            logger.info("IA rejeitou a conciliação.")
                    except Exception as e:
                        logger.error(f"❌ Erro pontual na IA: {e}")
                        continue 
                
                if match_found:
                    novos_matches.append({
                        'Data_Protheus': row_p['Data'],
                        'Historico': row_p['Historico'],
                        'Data_Banco': row_b['Data'],
                        'Descricao': row_b['Descricao'],
                        'Valor_Real': val,
                        'Metodo': metodo,
                        'Justificativa_Auditoria': justificativa
                    })
                    ids_p_removidos.add(row_p['Ref. Auditoria'])
                    ids_b_removidos.add(row_b['Ref. Auditoria'])
                    break 
    
    sobra_p_final = sobra_p[~sobra_p['Ref. Auditoria'].isin(ids_p_removidos)].copy()
    sobra_b_final = sobra_b[~sobra_b['Ref. Auditoria'].isin(ids_b_removidos)].copy()
    
    # Justificativas de Pendência
    def justificar_pendencia(row, df_comparacao):
        val = row['Valor_Real']
        if val in df_comparacao['Valor_Real'].values:
            return "Valor encontrado no outro extrato, mas datas ou descrições não bateram (IA Rejeitou ou Fora da Tolerância)."
        else:
            return "Valor Único: Não foi encontrado nenhum lançamento com este valor no outro extrato."

    if not sobra_p_final.empty:
        sobra_p_final['Motivo da Pendência'] = sobra_p_final.apply(lambda row: justificar_pendencia(row, df_b), axis=1)

    if not sobra_b_final.empty:
        sobra_b_final['Motivo da Pendência'] = sobra_b_final.apply(lambda row: justificar_pendencia(row, df_p), axis=1)

    df_novos = pd.DataFrame(novos_matches)
    logger.info(f"Conciliados via Lógica/IA: {len(df_novos)}")
    print(f"   -> {len(df_novos)} conciliados via Lógica Avançada/IA.")

    # --- RELATÓRIO FINAL ---
    caminho_saida = os.path.join(PASTA_OUTPUT, 'RELATORIO_ENTERPRISE_V2.xlsx')
    logger.info(f"Salvando relatório em: {caminho_saida}")
    print(f"\n💾 Salvando '{caminho_saida}'...")
    
    with pd.ExcelWriter(caminho_saida, engine='xlsxwriter') as writer:
        cols_conciliados = ['Data', 'Historico', 'Descricao', 'Valor_Real', 'Metodo', 'Justificativa_Auditoria']
        conciliados_exatos_limpo = conciliados.reindex(columns=cols_conciliados)
        
        if not df_novos.empty:
            conciliados_final = pd.concat([conciliados_exatos_limpo, df_novos])
        else:
            conciliados_final = conciliados_exatos_limpo
            
        conciliados_final.to_excel(writer, sheet_name='Conciliados', index=False)
        sobra_p_final.to_excel(writer, sheet_name='Pendencia Protheus', index=False)
        sobra_b_final.to_excel(writer, sheet_name='Pendencia Banco', index=False)
        
        workbook = writer.book
        fmt_text = workbook.add_format({'text_wrap': True})
        
        ws_conc = writer.sheets['Conciliados']
        ws_conc.set_column('F:F', 50, fmt_text)
        
        if 'Pendencia Protheus' in writer.sheets:
            writer.sheets['Pendencia Protheus'].set_column('E:E', 60, fmt_text)
        if 'Pendencia Banco' in writer.sheets:
            writer.sheets['Pendencia Banco'].set_column('E:E', 60, fmt_text)

    logger.info("✅ Processo Enterprise V3 Concluído com Sucesso.")
    print("✅ Processo Enterprise V3 Concluído.")

if __name__ == "__main__":
    start = time.time()
    pipeline_enterprise()
    print(f"⏱️ Tempo: {time.time() - start:.2f}s")