"""Validações de dados pessoais e de endereço, usadas no servidor.

O navegador repete parte destas regras (static/js/validacao.js) apenas para dar
retorno imediato; a decisão final é sempre do servidor.
"""

import re
import unicodedata
from difflib import SequenceMatcher

# DDDs válidos no Brasil (Anatel).
DDDS_VALIDOS = frozenset(
    {
        11, 12, 13, 14, 15, 16, 17, 18, 19,
        21, 22, 24, 27, 28,
        31, 32, 33, 34, 35, 37, 38,
        41, 42, 43, 44, 45, 46, 47, 48, 49,
        51, 53, 54, 55,
        61, 62, 63, 64, 65, 66, 67, 68, 69,
        71, 73, 74, 75, 77, 79,
        81, 82, 83, 84, 85, 86, 87, 88, 89,
        91, 92, 93, 94, 95, 96, 97, 98, 99,
    }
)

UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

_EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)[a-z0-9._%+\-]{1,64}(?<!\.)@"
    r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"
)
_NOME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ' .\-]+$")


def somente_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def cpf_valido(valor):
    """Formato (11 dígitos, não repetidos) e os dois dígitos verificadores."""
    cpf = somente_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11
        if digito == 10:
            digito = 0
        if digito != int(cpf[tamanho]):
            return False
    return True


def formatar_cpf(valor):
    cpf = somente_digitos(valor)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf


def validar_telefone(valor):
    """Retorna (dígitos, erro). Exige DDD válido e 10 (fixo) ou 11 (celular) dígitos."""
    digitos = somente_digitos(valor)
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) not in (10, 11):
        return None, "Informe o telefone com DDD: 10 dígitos (fixo) ou 11 (celular)."
    if int(digitos[:2]) not in DDDS_VALIDOS:
        return None, f"O DDD {digitos[:2]} não existe. Confira o código de área."
    if len(digitos) == 11 and digitos[2] != "9":
        return None, "Celulares com 11 dígitos começam com 9 depois do DDD."
    if len(digitos) == 10 and digitos[2] not in "2345":
        return None, "Telefones fixos começam com 2, 3, 4 ou 5 depois do DDD."
    if len(set(digitos[2:])) == 1:
        return None, "Informe um número de telefone real."
    return digitos, None


def formatar_telefone(digitos):
    d = somente_digitos(digitos)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d


def normalizar_email(valor):
    """Remove espaços, converte para minúsculas e valida o formato. Retorna (email, erro)."""
    email = unicodedata.normalize("NFKC", str(valor or "")).strip().casefold()
    if not email or len(email) > 160 or not _EMAIL_RE.fullmatch(email):
        return None, "Informe um e-mail válido, como nome@exemplo.com."
    return email, None


def validar_nome(valor, completo=False):
    """Mínimo de 2 caracteres e sem números. Com completo=True exige nome e sobrenome."""
    nome = " ".join(str(valor or "").split())
    if len(nome) < 2:
        return None, "O nome precisa ter pelo menos 2 caracteres."
    if len(nome) > 120:
        return None, "O nome pode ter no máximo 120 caracteres."
    if any(ch.isdigit() for ch in nome):
        return None, "O nome não pode conter números."
    if not _NOME_RE.fullmatch(nome):
        return None, "Use apenas letras, espaços, hífen ou apóstrofo no nome."
    if completo and len([p for p in nome.split() if len(p) >= 2]) < 2:
        return None, "Informe nome e sobrenome."
    return nome, None


def validar_cep(valor):
    cep = somente_digitos(valor)
    if len(cep) != 8 or cep == "00000000":
        return None, "Informe um CEP com 8 números."
    return cep, None


def formatar_cep(cep):
    d = somente_digitos(cep)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else d


def validar_numero(numero, sem_numero=False):
    """Número do imóvel obrigatório, a menos que 'sem número' seja marcado."""
    if sem_numero:
        return "", None
    texto = str(numero or "").strip()
    if not texto:
        return None, "Informe o número ou marque “sem número”."
    if len(texto) > 10 or not re.fullmatch(r"\d{1,6}[A-Za-z]?(?:[ -]?[A-Za-z0-9]{1,3})?", texto):
        return None, "Use apenas o número do imóvel (ex.: 120 ou 120A). Bloco e apto vão no complemento."
    return texto, None


def _normalizar_logradouro(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9 ]", " ", sem_acento.casefold())
    prefixos = r"^(rua|r|avenida|av|travessa|tv|alameda|al|estrada|est|praca|pc|rodovia|rod|largo|lgo|via|viela)\s+"
    base = re.sub(prefixos, "", " ".join(base.split()))
    base = re.sub(r"\b(de|da|do|das|dos|e)\b", " ", base)
    return " ".join(base.split())


def logradouro_diverge(digitado, oficial, limite=0.72):
    """True quando o logradouro digitado difere bastante do retornado pelo ViaCEP."""
    a, b = _normalizar_logradouro(digitado), _normalizar_logradouro(oficial)
    if not a or not b:
        return False
    if a in b or b in a:
        return False
    return SequenceMatcher(None, a, b).ratio() < limite


def normalizar_texto(texto):
    return (
        unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().casefold().strip()
    )
