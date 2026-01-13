import unicodedata

def normalizar_coluna(text, capitalize: bool = False) -> str:
    """Remove acentos, espaços extras e padroniza para minúsculo."""
    if not isinstance(text, str):
        return str(text).lower().strip()
    
    # Normalização NFKD: Decompõe caracteres (ex: 'ç' vira 'c' + ',')
    # e remove os acentos (non-spacing marks)
    text = "".join(
        c for c in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(c)
    )
    
    if capitalize:
        return text.strip().capitalize()
    
    return text.lower().strip()