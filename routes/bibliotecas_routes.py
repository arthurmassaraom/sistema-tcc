import re
import requests
from flask import Blueprint, current_app, jsonify, render_template, request
from models.biblioteca import Biblioteca

bibliotecas_bp = Blueprint("bibliotecas", __name__)


PERIODOS = {"manha": "Manhã", "tarde": "Tarde", "noite": "Noite"}


@bibliotecas_bp.get("/bibliotecas")
def bibliotecas():
    todas = Biblioteca.query.order_by(Biblioteca.estado, Biblioteca.cidade, Biblioteca.nome).all()
    cidades = sorted({(b.cidade, b.estado) for b in todas})
    cidade = request.args.get("cidade", "").strip()
    periodo = request.args.get("periodo", "").strip()
    filtradas = todas
    if cidade:
        filtradas = [b for b in filtradas if f"{b.cidade}/{b.estado}" == cidade]
    if periodo in PERIODOS:
        filtradas = [b for b in filtradas if b.atende_periodo(periodo)]
    selecionada = None
    if request.args.get("unidade", "").isdigit():
        selecionada = next((b for b in todas if b.id == int(request.args["unidade"])), None)
    return render_template(
        "bibliotecas.html",
        bibliotecas=filtradas,
        total_rede=len(todas),
        cidades=cidades,
        cidade=cidade,
        periodo=periodo,
        periodos=PERIODOS,
        selecionada=selecionada or (filtradas[0] if filtradas else None),
        mapas_ativos=bool(current_app.config.get("GOOGLE_MAPS_API_KEY")),
    )


@bibliotecas_bp.get("/api/cep/<cep>")
def consulta_cep(cep):
    cep_limpo = re.sub(r"\D", "", cep)
    if len(cep_limpo) != 8:
        return jsonify({"erro": "Informe um CEP válido com 8 números."}), 400
    try:
        response = requests.get(f"https://viacep.com.br/ws/{cep_limpo}/json/", timeout=6)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return jsonify({"erro": "Não foi possível consultar o ViaCEP agora."}), 502
    if not isinstance(data, dict):
        return jsonify({"erro": "O serviço de CEP retornou uma resposta inválida."}), 502
    expected_text_fields = ("cep", "logradouro", "bairro", "localidade", "uf")
    if any(
        data.get(field) is not None and not isinstance(data.get(field), str)
        for field in expected_text_fields
    ):
        return jsonify({"erro": "O serviço de CEP retornou dados em formato inválido."}), 502
    if data.get("erro"):
        return jsonify({"erro": "CEP não encontrado."}), 404

    cidade, uf = (data.get("localidade") or "").casefold(), (data.get("uf") or "").upper()
    locais = Biblioteca.query.order_by(Biblioteca.nome).all()
    same_city = [b for b in locais if b.estado.upper() == uf and b.cidade.casefold() == cidade]
    same_city_ids = {b.id for b in same_city}
    same_state = [b for b in locais if b.estado.upper() == uf and b.id not in same_city_ids]
    other = [b for b in locais if b.estado.upper() != uf]

    def dump(b, badge=None):
        return {
            "nome": b.nome,
            "cep": b.cep,
            "endereco": b.endereco,
            "cidade": b.cidade,
            "estado": b.estado,
            "telefone": b.telefone,
            "horario": b.horario,
            "id": b.id,
            "badge": badge,
        }

    nearby = [dump(b, "Mais próxima da sua cidade") for b in same_city]
    within_state = [dump(b, "Mesmo estado") for b in same_state]
    others = [dump(b, "Outra região") for b in other]
    return jsonify(
        {
            "endereco": {
                "cep": data.get("cep"),
                "logradouro": data.get("logradouro"),
                "bairro": data.get("bairro"),
                "cidade": data.get("localidade"),
                "estado": uf,
            },
            "mesma_cidade": nearby,
            "mesmo_estado": within_state,
            "outras_regioes": others,
        }
    )
