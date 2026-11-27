"""Consulta de CEP (ViaCEP) e geocodificação no servidor (Google Geocoding API).

- A chave GOOGLE_MAPS_API_KEY é lida de config.py e usada apenas aqui, no servidor.
  Nunca é enviada ao navegador nem registrada em logs.
- Resultados de geocodificação ficam em cache na tabela geo_cache.
- Sem chave configurada, as funções degradam: retornam erro amigável e o
  checkout continua funcionando apenas com a validação do ViaCEP.
"""

import math
import time

import requests
from flask import current_app

from database import db
from models.interacoes import GeoCache
from services.validacao import normalizar_texto

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

MENSAGENS_GOOGLE = {
    "ZERO_RESULTS": "Não encontramos esse endereço no mapa. Confira o número e o logradouro.",
    "OVER_QUERY_LIMIT": "O serviço de mapas atingiu o limite de consultas. Tente novamente em alguns minutos.",
    "OVER_DAILY_LIMIT": "O serviço de mapas atingiu o limite diário de consultas.",
    "REQUEST_DENIED": "O serviço de mapas recusou a consulta. A chave de API precisa ser revisada pela administração.",
    "INVALID_REQUEST": "A consulta ao mapa ficou incompleta. Confira o CEP e o número.",
    "UNKNOWN_ERROR": "O serviço de mapas teve uma falha temporária. Tente novamente.",
}

_viacep_cache = {}
_VIACEP_TTL = 6 * 3600


class GeoErro(Exception):
    def __init__(self, mensagem, status=502, codigo="erro"):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.codigo = codigo


def mapas_ativos():
    return bool(current_app.config.get("GOOGLE_MAPS_API_KEY"))


def consultar_viacep(cep):
    """Retorna o endereço do CEP (8 dígitos) ou levanta GeoErro."""
    agora = time.monotonic()
    em_cache = _viacep_cache.get(cep)
    if em_cache and agora - em_cache[0] < _VIACEP_TTL:
        return dict(em_cache[1])
    try:
        resposta = requests.get(VIACEP_URL.format(cep=cep), timeout=6)
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeoErro("Não foi possível consultar o ViaCEP agora.", 502, "rede") from exc
    if not isinstance(dados, dict):
        raise GeoErro("O serviço de CEP retornou uma resposta inválida.", 502, "resposta")
    campos = ("cep", "logradouro", "bairro", "localidade", "uf")
    if any(dados.get(c) is not None and not isinstance(dados.get(c), str) for c in campos):
        raise GeoErro("O serviço de CEP retornou dados em formato inválido.", 502, "resposta")
    if dados.get("erro"):
        raise GeoErro("CEP não encontrado. Confira os números digitados.", 404, "cep_inexistente")
    endereco = {
        "cep": dados.get("cep") or f"{cep[:5]}-{cep[5:]}",
        "logradouro": dados.get("logradouro") or "",
        "bairro": dados.get("bairro") or "",
        "cidade": dados.get("localidade") or "",
        "estado": (dados.get("uf") or "").upper(),
    }
    _viacep_cache[cep] = (agora, endereco)
    return dict(endereco)


def area_atendida(cidade, uf):
    """Verifica a área de entrega configurada (DELIVERY_STATES / DELIVERY_CITIES)."""
    estados = current_app.config.get("DELIVERY_STATES") or []
    cidades = current_app.config.get("DELIVERY_CITIES") or []
    if estados and (uf or "").upper() not in estados:
        return False, f"Ainda não entregamos em {uf}. Atendemos: {', '.join(estados)}. Escolha a retirada em uma biblioteca parceira."
    if cidades and normalizar_texto(cidade) not in {normalizar_texto(c) for c in cidades}:
        return False, f"Ainda não entregamos em {cidade}. Cidades atendidas: {', '.join(cidades)}."
    return True, None


def _chave_cache(consulta):
    return normalizar_texto(" ".join(str(consulta).split()))[:255]


def geocodificar(consulta, cep):
    """Geocodifica um endereço textual com cache. Retorna dict ou levanta GeoErro."""
    chave = _chave_cache(consulta)
    em_cache = GeoCache.query.filter_by(chave=chave).first()
    if em_cache:
        if em_cache.status != "OK":
            raise GeoErro(MENSAGENS_GOOGLE.get(em_cache.status, MENSAGENS_GOOGLE["UNKNOWN_ERROR"]), 404, em_cache.status)
        return {
            "lat": em_cache.latitude,
            "lng": em_cache.longitude,
            "location_type": em_cache.location_type,
            "endereco_formatado": em_cache.endereco_formatado,
            "cache": True,
        }
    api_key = current_app.config.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise GeoErro("O mapa não está configurado neste ambiente.", 503, "sem_chave")
    try:
        resposta = requests.get(
            GEOCODE_URL,
            params={"address": consulta, "key": api_key, "region": "br", "language": "pt-BR"},
            timeout=(4, 8),
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except (requests.RequestException, ValueError) as exc:
        # Não registramos a URL: ela contém a chave.
        current_app.logger.warning("Falha de rede na geocodificação (%s).", type(exc).__name__)
        raise GeoErro("Não foi possível falar com o serviço de mapas. Verifique a conexão e tente de novo.", 502, "rede") from None
    status = str(dados.get("status", "UNKNOWN_ERROR")) if isinstance(dados, dict) else "UNKNOWN_ERROR"
    if status != "OK" or not dados.get("results"):
        if status == "ZERO_RESULTS":
            db.session.add(GeoCache(chave=chave, cep=cep, status=status))
            db.session.commit()
        current_app.logger.info("Geocodificação retornou %s.", status)
        codigo_http = 404 if status == "ZERO_RESULTS" else 503 if status in ("OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT", "REQUEST_DENIED") else 502
        raise GeoErro(MENSAGENS_GOOGLE.get(status, MENSAGENS_GOOGLE["UNKNOWN_ERROR"]), codigo_http, status)
    primeiro = dados["results"][0]
    geometria = primeiro.get("geometry", {})
    local = geometria.get("location", {})
    try:
        lat, lng = float(local["lat"]), float(local["lng"])
    except (KeyError, TypeError, ValueError):
        raise GeoErro(MENSAGENS_GOOGLE["UNKNOWN_ERROR"], 502, "resposta") from None
    registro = GeoCache(
        chave=chave,
        cep=cep,
        latitude=lat,
        longitude=lng,
        location_type=str(geometria.get("location_type", ""))[:30],
        endereco_formatado=str(primeiro.get("formatted_address", ""))[:300],
        status="OK",
    )
    db.session.add(registro)
    db.session.commit()
    return {
        "lat": lat,
        "lng": lng,
        "location_type": registro.location_type,
        "endereco_formatado": registro.endereco_formatado,
        "cache": False,
    }


def consulta_cep(endereco):
    return f"{endereco['cep']}, {endereco['cidade']} - {endereco['estado']}, Brasil"


def consulta_endereco(endereco, numero):
    partes = [endereco.get("logradouro") or ""]
    if numero:
        partes[0] = f"{partes[0]}, {numero}"
    partes += [endereco.get("bairro") or "", f"{endereco['cidade']} - {endereco['estado']}", endereco["cep"], "Brasil"]
    return ", ".join(p for p in partes if p)


def distancia_km(a, b):
    """Distância em linha reta (Haversine) entre dois pontos {lat, lng}."""
    raio = 6371.0
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return round(2 * raio * math.asin(math.sqrt(h)), 2)


def mapa_embed_url(lat, lng, zoom=16):
    """URL pública de incorporação do Google Maps (não usa nem expõe a chave de API)."""
    return f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}&z={zoom}&hl=pt-BR&output=embed"


def geolocalizar_biblioteca(biblioteca):
    """Coordenadas da unidade (salvas no registro após a primeira consulta)."""
    if biblioteca.latitude is not None and biblioteca.longitude is not None:
        return {"lat": biblioteca.latitude, "lng": biblioteca.longitude}
    consulta = f"{biblioteca.endereco}, {biblioteca.cidade} - {biblioteca.estado}, {biblioteca.cep}, Brasil"
    ponto = geocodificar(consulta, "".join(filter(str.isdigit, biblioteca.cep or ""))[:8] or "00000000")
    biblioteca.latitude, biblioteca.longitude = ponto["lat"], ponto["lng"]
    db.session.commit()
    return {"lat": ponto["lat"], "lng": ponto["lng"]}
