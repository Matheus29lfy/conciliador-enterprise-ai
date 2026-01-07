import requests
import json
import logging
import re
from typing import Dict, Any, Optional

# --- CONFIGURAÇÃO ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MODELO_PERMITIDO = "llama3.2"
URL_OLLAMA = "http://localhost:11434/api/generate"
TIMEOUT_SEGUNDOS = 30
MAX_CARACTERES_PROMPT = 1000

BLACKLIST_KEYWORDS = ["IGNORE ALL", "SYSTEM OVERRIDE", "DELETE", "DROP TABLE"]

def sanitizar_entrada(texto: str) -> str:
    if not texto:
        raise ValueError("Entrada vazia não permitida.")
    if len(texto) > MAX_CARACTERES_PROMPT:
        logger.warning(f"Entrada truncada! Recebido: {len(texto)} chars.")
        texto = texto[:MAX_CARACTERES_PROMPT]
    for word in BLACKLIST_KEYWORDS:
        if word.lower() in texto.lower():
            logger.warning(f"Tentativa de injeção detectada: {word}")
            texto = re.sub(word, "", texto, flags=re.IGNORECASE)
    return texto.strip()

# [AJUSTE 1] Adicionado retorno explícito -> bool
def validar_disponibilidade_modelo() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code == 200:
            modelos = [m['name'] for m in resp.json()['models']]
            if not any(MODELO_PERMITIDO in m for m in modelos):
                logger.critical(f"Modelo '{MODELO_PERMITIDO}' não encontrado!")
                return False
            return True
        return False
    except requests.exceptions.ConnectionError:
        logger.critical("OLLAMA NÃO DETECTADO. Verifique se o app está rodando.")
        return False

# Função auxiliar para validar regras de negócio (Schema Validation)
def validar_conteudo_negocio(dados: Dict[str, Any]):
    # [AJUSTE 3] Validação de Tipo: match deve ser bool
    if not isinstance(dados.get('match'), bool):
        raise ValueError(f"Campo 'match' inválido. Esperado bool, recebido: {type(dados.get('match'))}")

    # [AJUSTE 3] Validação de Valor: confianca deve ser um dos permitidos
    valores_confianca = ['alta', 'media', 'baixa']
    conf = dados.get('confianca', '').lower() # Normaliza para minúsculo
    if conf not in valores_confianca:
        raise ValueError(f"Campo 'confianca' inválido ('{conf}'). Permitidos: {valores_confianca}")
    # Atualiza o dado normalizado
    dados['confianca'] = conf

    # [AJUSTE 3] Validação de Conteúdo: justificativa deve ser string não vazia
    just = dados.get('justificativa')
    if not isinstance(just, str) or len(just.strip()) == 0:
        raise ValueError("Campo 'justificativa' deve ser um texto não vazio.")

def extrair_validar_json(texto_bruto: str) -> Dict[str, Any]:
    try:
        # [AJUSTE 2] Validação de resposta vazia antes de processar
        if not texto_bruto or not texto_bruto.strip():
            raise ValueError("A IA retornou uma resposta vazia.")

        inicio = texto_bruto.find('{')
        fim = texto_bruto.rfind('}') + 1
        
        if inicio == -1 or fim == 0:
            raise ValueError("Nenhum JSON encontrado na resposta.")
            
        json_str = texto_bruto[inicio:fim]
        dados = json.loads(json_str)
        
        # Validação Estrutural (Campos existem?)
        campos_obrigatorios = ["match", "confianca", "justificativa"]
        if not all(campo in dados for campo in campos_obrigatorios):
            raise ValueError(f"JSON incompleto. Campos esperados: {campos_obrigatorios}")
        
        # Validação Semântica (Os dados fazem sentido?)
        validar_conteudo_negocio(dados)
            
        return dados
        
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Falha na validação da resposta: {e}")
        logger.debug(f"Payload recusado: {texto_bruto}")
        raise

def consultar_agente_blindado(transacao_a: str, transacao_b: str) -> Optional[Dict]:
    if not validar_disponibilidade_modelo():
        return None

    try:
        t_a_clean = sanitizar_entrada(transacao_a)
        t_b_clean = sanitizar_entrada(transacao_b)

        prompt = f"""
        Analise estas transações.
        A: {t_a_clean}
        B: {t_b_clean}
        
        Responda APENAS JSON:
        {{ "match": boolean, "confianca": "alta/media/baixa", "justificativa": "string" }}
        """

        payload = {
            "model": MODELO_PERMITIDO,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0, # <--- ADICIONE ISSO: Criatividade Zero
                "seed": 123 # <--- ADICIONE ISSO: Semente fixa para repetibilidade
            }
        }

        logger.info("Enviando requisição ao Agente IA...")
        response = requests.post(URL_OLLAMA, json=payload, timeout=TIMEOUT_SEGUNDOS)
        response.raise_for_status()

        resposta_ia = response.json().get('response', '')
        
        # Chama a nova função de extração blindada
        dados_validados = extrair_validar_json(resposta_ia)
        
        logger.info(f"Análise concluída. Match: {dados_validados['match']}")
        return dados_validados

    except Exception as e:
        logger.error(f"Erro no pipeline: {e}")
        return None

if __name__ == "__main__":
    # Teste de robustez
    print("--- Teste de Validação de Tipos ---")
    t1 = "PGTO FORNECEDOR 123"
    t2 = "PIX ENVIADO FORNECEDOR 123"
    
    res = consultar_agente_blindado(t1, t2)
    if res:
        print(json.dumps(res, indent=4, ensure_ascii=False))