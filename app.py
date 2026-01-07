import streamlit as st
import pandas as pd
import os
import time
import shutil
import logging
from datetime import datetime

# --- IMPORTAÇÃO DO BACKEND ---
from conciliador_enterprise_v2 import pipeline_enterprise, PASTA_LOGS, PASTA_OUTPUT, PASTA_INPUT

# --- CONFIGURAÇÃO DE SEGURANÇA ---
MAX_FILE_SIZE_MB = 50
MAX_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Conciliador Enterprise AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #0068c9; }
    /* Ajuste para mensagens de erro ficarem mais visíveis */
    .stAlert { font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE SEGURANÇA E UTILITÁRIOS ---

def validar_permissoes():
    """Verifica se temos permissão de escrita antes de começar."""
    pastas = [PASTA_INPUT, PASTA_OUTPUT, PASTA_LOGS]
    for p in pastas:
        os.makedirs(p, exist_ok=True)
        if not os.access(p, os.W_OK):
            st.error(f"❌ ERRO CRÍTICO: Sem permissão de escrita na pasta '{p}'. Execute como Administrador.")
            st.stop()

def rotacionar_logs():
    """Faz backup do log anterior em vez de apagar."""
    log_path = os.path.join(PASTA_LOGS, "execucao.log")
    if os.path.exists(log_path):
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"execucao_backup_{timestamp}.log"
            shutil.move(log_path, os.path.join(PASTA_LOGS, backup_name))
        except Exception as e:
            logging.warning(f"Não foi possível rotacionar log: {e}")

def validar_integridade_basica(uploaded_file):
    """Valida tamanho e se é um Excel legível."""
    if uploaded_file.size > MAX_BYTES:
        st.error(f"❌ O arquivo '{uploaded_file.name}' excede o limite de {MAX_FILE_SIZE_MB}MB.")
        return False
    
    try:
        # Tenta ler apenas o cabeçalho para ver se não está corrompido
        pd.read_excel(uploaded_file, nrows=0)
        return True
    except Exception:
        st.error(f"❌ O arquivo '{uploaded_file.name}' está corrompido ou não é um Excel válido.")
        return False

def validar_assinatura_arquivo(uploaded_file, tipo_esperado):
    """
    (NOVO) Fingerprinting: Verifica se as colunas correspondem ao tipo de arquivo esperado.
    Impede que o usuário coloque o arquivo do Banco no lugar do Protheus.
    """
    try:
        # Lê apenas o cabeçalho
        df = pd.read_excel(uploaded_file, nrows=0)
        colunas = [c.lower() for c in df.columns]
        
        # Regras para PROTHEUS
        if tipo_esperado == "Protheus":
            # Deve ter 'natureza' (para saber D/C) ou 'historico'
            if "natureza" not in colunas and "historico" not in colunas:
                return False, "Arquivo inválido para Protheus. Faltam colunas obrigatórias ('Natureza' ou 'Historico')."
            # Não deve ter 'descricao' (típico de extrato bancário)
            if "descricao" in colunas and "natureza" not in colunas:
                return False, "⚠️ Parece que você enviou um Extrato Bancário no campo do Protheus. Verifique."

        # Regras para BANCO
        elif tipo_esperado == "Banco":
            # Deve ter 'descricao' ou 'saldo' ou 'documento'
            if "descricao" not in colunas and "saldo" not in colunas:
                return False, "Arquivo inválido para Banco. Falta coluna 'Descricao'."
            # Não deve ter 'natureza' (típico de ERP)
            if "natureza" in colunas:
                return False, "⚠️ Parece que você enviou um relatório do Protheus no campo do Banco. Verifique."
                
        return True, ""
        
    except Exception as e:
        return False, f"Erro ao validar colunas: {e}"

def salvar_upload_seguro(uploaded_file, nome_destino):
    """Salva com tratamento de erro de IO."""
    try:
        caminho_completo = os.path.join(PASTA_INPUT, nome_destino)
        # O 'wb' garante que o arquivo antigo seja sobrescrito completamente
        with open(caminho_completo, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return True
    except Exception as e:
        st.error(f"Erro ao salvar arquivo em disco: {e}")
        return False

# --- INICIALIZAÇÃO DE ESTADO ---
if 'processando' not in st.session_state:
    st.session_state['processando'] = False

# --- BARRA LATERAL ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2910/2910795.png", width=60)
    st.title("Painel de Auditoria")
    st.markdown("---")
    
    validar_permissoes()

    st.subheader("1. Carregar Dados")
    uploaded_protheus = st.file_uploader("Relatório Protheus (.xlsx)", type="xlsx", disabled=st.session_state['processando'])
    uploaded_banco = st.file_uploader("Extrato Bancário (.xlsx)", type="xlsx", disabled=st.session_state['processando'])
    
    st.markdown("---")
    st.caption("v4.0.0 - Enterprise Secure")

# --- ÁREA PRINCIPAL ---
st.title("Conciliação Bancária com IA Generativa")

if uploaded_protheus and uploaded_banco:
    
    # 1. Validação Básica (Tamanho/Corrupção)
    if not validar_integridade_basica(uploaded_protheus) or not validar_integridade_basica(uploaded_banco):
        st.stop()

    # 2. Validação de Negócio (Fingerprinting - NOVO)
    ok_p, msg_p = validar_assinatura_arquivo(uploaded_protheus, "Protheus")
    ok_b, msg_b = validar_assinatura_arquivo(uploaded_banco, "Banco")

    erro_validacao = False
    if not ok_p:
        st.error(f"❌ Erro no arquivo Protheus: {msg_p}")
        erro_validacao = True
        
    if not ok_b:
        st.error(f"❌ Erro no arquivo Banco: {msg_b}")
        erro_validacao = True
    
    if erro_validacao:
        st.stop() # Bloqueia o botão de iniciar se os arquivos estiverem trocados

    # Se passou por tudo, libera a interface
    col_status, col_btn = st.columns([3, 1])
    
    with col_status:
        st.success("✅ Arquivos validados e assinaturas conferidas.")
        
    with col_btn:
        iniciar = st.button(
            "🚀 INICIAR AUDITORIA", 
            type="primary", 
            disabled=st.session_state['processando']
        )

    if iniciar:
        st.session_state['processando'] = True
        
        try:
            # Preparação e Backup
            rotacionar_logs()
            
            if salvar_upload_seguro(uploaded_protheus, "sistema_protheus.xlsx") and \
               salvar_upload_seguro(uploaded_banco, "extrato_banco.xlsx"):

                # Execução do Motor
                with st.status("🔄 Executando Motor de Conciliação...", expanded=True) as status:
                    st.write("⚙️ Inicializando pipelines seguros...")
                    st.write("📂 Validando schema dos dados...")
                    time.sleep(0.5)
                    
                    st.write("🤖 Acionando Agente IA (Llama 3.2)...")
                    
                    start_time = time.time()
                    try:
                        # Chama o Backend
                        pipeline_enterprise()
                        
                        tempo = time.time() - start_time
                        status.update(label=f"✅ Concluído em {tempo:.2f}s", state="complete", expanded=False)
                        
                    except Exception as e:
                        status.update(label="❌ Erro na Execução", state="error")
                        st.error(f"Falha no Backend: {e}")
                        st.session_state['processando'] = False
                        st.stop()

                # Exibição de Resultados
                arquivo_final = os.path.join(PASTA_OUTPUT, 'RELATORIO_ENTERPRISE_V2.xlsx')
                if os.path.exists(arquivo_final):
                    st.divider()
                    
                    try:
                        df_conciliados = pd.read_excel(arquivo_final, sheet_name='Conciliados')
                        df_pend_prot = pd.read_excel(arquivo_final, sheet_name='Pendencia Protheus')
                        df_pend_banco = pd.read_excel(arquivo_final, sheet_name='Pendencia Banco')

                        # Dashboard de KPIs
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Volume Conciliado", f"R$ {df_conciliados['Valor_Real'].sum():,.2f}")
                        k2.metric("Itens Conciliados", len(df_conciliados))
                        
                        qtd_ia = 0
                        if 'Metodo' in df_conciliados.columns:
                            qtd_ia = len(df_conciliados[df_conciliados['Metodo'] == 'Inteligência Artificial'])
                        k3.metric("Recuperados por IA", qtd_ia)
                        k4.metric("Pendências Totais", len(df_pend_prot) + len(df_pend_banco), delta_color="inverse")

                        # Tabelas
                        t1, t2, t3 = st.tabs(["✅ Conciliados", "⚠️ Pend. Protheus", "⚠️ Pend. Banco"])
                        with t1: st.dataframe(df_conciliados, use_container_width=True, hide_index=True)
                        with t2: st.dataframe(df_pend_prot, use_container_width=True, hide_index=True)
                        with t3: st.dataframe(df_pend_banco, use_container_width=True, hide_index=True)

                        # Download
                        timestamp_safe = datetime.now().strftime('%Y%m%d_%H%M%S')
                        with open(arquivo_final, "rb") as f:
                            st.download_button(
                                label="📥 BAIXAR RELATÓRIO OFICIAL",
                                data=f,
                                file_name=f"Auditoria_{timestamp_safe}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                    except Exception as e:
                        st.error(f"Erro ao ler relatório final: {e}")

        finally:
            st.session_state['processando'] = False
            if st.button("🔄 Novo Processamento"):
                st.rerun()

else:
    st.info("👈 Faça upload dos arquivos para começar.")