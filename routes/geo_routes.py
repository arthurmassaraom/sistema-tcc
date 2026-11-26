"""API de geolocalização: CEP, área de atendimento, mapa e distância até bibliotecas.

A chave do Google fica apenas no servidor; o navegador recebe somente coordenadas,
mensagens e uma URL pública de incorporação do mapa.
"""

from flask import Blueprint, current_app, jsonify, request, session

from database import db
from models.biblioteca import Biblioteca
from services.geo import (
    GeoErro,
    area_atendida,
    consulta_cep,
    consulta_endereco,
    consultar_viacep,
    distancia_km,
    geocodificar,
    geolocalizar_biblioteca,
    mapa_embed_url,
    mapas_ativos,
)
from services.validacao import logradouro_diverge, validar_cep, validar_numero

geo_bp = Blueprint("geo", __name__, url_prefix="/api/geo")


@geo_bp.get("/<cep>")
def geo_cep(cep):
    cep_limpo, erro = validar_cep(cep)
    if erro:
        return jsonify(ok=False, erro=erro, codigo="cep_formato"), 400
    numero_bruto = request.args.get("numero", "").strip()[:10]
    sem_numero = request.args.get("sem_numero") in ("1", "true")
    logradouro_digitado = request.args.get("logradouro", "").strip()[:160]
    if (numero_bruto or sem_numero) and not session.get("usuario_id"):
        # Geocodificação no nível do imóvel só para quem está no checkout ou no perfil.
        return jsonify(ok=False, erro="Entre na sua conta para localizar o endereço completo."), 401

    try:
        endereco = consultar_viacep(cep_limpo)
    except GeoErro as exc:
        return jsonify(ok=False, erro=exc.mensagem, codigo=exc.codigo), exc.status

    atendido, motivo_area = area_atendida(endereco["cidade"], endereco["estado"])
    resposta = {
        "ok": True,
        "endereco": endereco,
        "atendido": atendido,
        "area_mensagem": motivo_area,
        "logradouro_divergente": bool(
            logradouro_digitado
            and endereco["logradouro"]
            and logradouro_diverge(logradouro_digitado, endereco["logradouro"])
        ),
        "mapas_ativos": mapas_ativos(),
        "mapa": None,
        "aviso": None,
    }
    if resposta["logradouro_divergente"]:
        resposta["aviso"] = (
            f"O CEP {endereco['cep']} corresponde a “{endereco['logradouro']}”. "
            "Confirme se o logradouro digitado está correto."
        )

    numero = None
    if numero_bruto and not sem_numero:
        numero, erro_numero = validar_numero(numero_bruto)
        if erro_numero:
            resposta["numero_erro"] = erro_numero
            numero = None

    if not mapas_ativos():
        resposta["mapa_mensagem"] = "Mapa indisponível: a chave do Google Maps não está configurada."
        return jsonify(resposta)

    try:
        centro = geocodificar(consulta_cep(endereco), cep_limpo)
    except GeoErro as exc:
        resposta["mapa_mensagem"] = exc.mensagem
        return jsonify(resposta)

    ponto = centro
    preciso = False
    if numero:
        try:
            ponto = geocodificar(consulta_endereco(endereco, numero), cep_limpo)
            preciso = ponto.get("location_type") == "ROOFTOP"
        except GeoErro as exc:
            resposta["mapa_mensagem"] = exc.mensagem
            ponto = centro
    distancia = distancia_km(centro, ponto) if ponto is not centro else 0.0
    limite = float(current_app.config.get("GEO_ALERT_KM", 2))
    resposta["mapa"] = {
        "lat": ponto["lat"],
        "lng": ponto["lng"],
        "preciso": preciso,
        "location_type": ponto.get("location_type"),
        "legenda": "Localização exata do endereço" if preciso else "Localização aproximada do CEP",
        "embed_url": mapa_embed_url(ponto["lat"], ponto["lng"], 17 if preciso else 15),
        "distancia_centro_km": distancia,
        "pino_distante": distancia > limite,
    }
    if distancia > limite:
        resposta["aviso"] = (
            f"O ponto encontrado fica a {str(distancia).replace('.', ',')} km do centro do CEP. "
            "Confira o número e o CEP antes de continuar."
        )
    return jsonify(resposta)


@geo_bp.get("/distancia")
def distancia_biblioteca():
    """Distância entre um CEP e uma biblioteca parceira (para avisar na retirada)."""
    cep_limpo, erro = validar_cep(request.args.get("cep", ""))
    if erro:
        return jsonify(ok=False, erro=erro), 400
    try:
        biblioteca = db.session.get(Biblioteca, int(request.args.get("biblioteca_id", "")))
    except (TypeError, ValueError):
        biblioteca = None
    if not biblioteca:
        return jsonify(ok=False, erro="Biblioteca não encontrada."), 404
    try:
        endereco = consultar_viacep(cep_limpo)
    except GeoErro as exc:
        return jsonify(ok=False, erro=exc.mensagem), exc.status
    mesma_cidade = (
        endereco["cidade"].casefold() == biblioteca.cidade.casefold()
        and endereco["estado"] == biblioteca.estado.upper()
    )
    resposta = {"ok": True, "km": None, "longe": not mesma_cidade, "aproximado": True}
    if mapas_ativos():
        try:
            origem = geocodificar(consulta_cep(endereco), cep_limpo)
            destino = geolocalizar_biblioteca(biblioteca)
            km = distancia_km(origem, destino)
            limite = float(current_app.config.get("PICKUP_ALERT_KM", 15))
            resposta.update(km=km, longe=km > limite)
        except GeoErro:
            pass
    if resposta["longe"]:
        resposta["mensagem"] = (
            f"Atenção: {biblioteca.nome} fica a cerca de {str(resposta['km']).replace('.', ',')} km do CEP informado."
            if resposta["km"] is not None
            else f"Atenção: {biblioteca.nome} fica em {biblioteca.cidade}/{biblioteca.estado}, fora da sua cidade."
        )
    else:
        resposta["mensagem"] = (
            f"{biblioteca.nome} fica a cerca de {str(resposta['km']).replace('.', ',')} km de você."
            if resposta["km"] is not None
            else f"{biblioteca.nome} fica na sua cidade."
        )
    return jsonify(resposta)
