from datetime import date, timedelta
from functools import wraps
import math
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from database import db
from models.usuario import Usuario
from models.livro import Livro
from models.doacao import Doacao
from models.biblioteca import Biblioteca
from services.email import enviar_email
from models.transacao import Transacao

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        usuario = (
            db.session.get(
                Usuario,
                session.get("usuario_id"),
            )
            if session.get("usuario_id")
            else None
        )
        if not usuario or not usuario.is_admin:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


def _save_book(form, book=None):
    titulo, autor = form.get("titulo", "").strip(), form.get("autor", "").strip()
    if not titulo or not autor:
        raise ValueError("Título e autor são obrigatórios.")
    try:
        estoque = int(form.get("estoque", "0"))
        ano = int(form.get("ano")) if form.get("ano", "").strip() else None
        preco_venda = float(form.get("preco_venda", "0").replace(",", "."))
        preco_aluguel = float(form.get("preco_aluguel", "0").replace(",", "."))
    except ValueError as exc:
        raise ValueError("Ano, estoque e preços devem ser numéricos.") from exc
    if (
        estoque < 0
        or not math.isfinite(preco_venda)
        or not math.isfinite(preco_aluguel)
        or preco_venda < 0
        or preco_aluguel < 0
    ):
        raise ValueError("Estoque e preços devem ser válidos e não negativos.")
    if len(titulo) > 200 or len(autor) > 160:
        raise ValueError("Título e autor excedem o limite de caracteres permitido.")
    if ano is not None and not 1000 <= ano <= 2100:
        raise ValueError("Informe um ano entre 1000 e 2100.")
    book = book or Livro()
    book.titulo, book.autor = titulo, autor
    book.editora = form.get("editora", "").strip()
    book.ano = ano
    book.isbn = form.get("isbn", "").strip() or None
    book.genero = form.get("genero", "Geral").strip() or "Geral"
    book.categoria = form.get("categoria", "Geral").strip() or "Geral"
    book.modalidade = form.get("modalidade", "Ambos")
    if book.modalidade not in ("Ambos", "Venda", "Aluguel"):
        raise ValueError("Modalidade inválida.")
    book.estoque, book.preco_venda, book.preco_aluguel = estoque, preco_venda, preco_aluguel
    book.resumo = (
        form.get(
            "resumo",
            "",
        ).strip()
        or "Uma leitura selecionada pelo acervo comunitário."
    )
    book.avaliacao = 0  # campo legado: avaliações exibidas são sempre calculadas dos usuários.
    if not book.id:
        book.ativo = True
    return book


def _save_biblioteca(form, biblioteca=None):
    nome = form.get("nome", "").strip()
    cep = re.sub(r"\D", "", form.get("cep", ""))
    endereco = form.get("endereco", "").strip()
    cidade = form.get("cidade", "").strip()
    estado = form.get("estado", "").strip().upper()
    telefone = form.get("telefone", "").strip()
    if not nome or len(nome) > 160 or len(cep) != 8 or not endereco or len(endereco) > 200:
        raise ValueError("Informe nome, CEP válido e endereço da unidade.")
    if not cidade or len(cidade) > 100 or not re.fullmatch(r"[A-Z]{2}", estado):
        raise ValueError("Informe uma cidade e uma UF válida com duas letras.")
    if len(telefone) > 30:
        raise ValueError("O telefone deve ter até 30 caracteres.")
    abertura = form.get("horario_abertura", "").strip()
    fechamento = form.get("horario_fechamento", "").strip()
    dias = " ".join(form.get("dias_funcionamento", "").split())[:80]
    for valor in (abertura, fechamento):
        if valor and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", valor):
            raise ValueError("Use horários no formato HH:MM, como 09:00.")
    if bool(abertura) != bool(fechamento):
        raise ValueError("Informe abertura e fechamento, ou deixe os dois em branco.")
    if abertura and abertura >= fechamento:
        raise ValueError("O horário de fechamento deve ser depois da abertura.")
    biblioteca = biblioteca or Biblioteca()
    endereco_anterior = (biblioteca.endereco, biblioteca.cep)
    biblioteca.nome = nome
    biblioteca.cep = f"{cep[:5]}-{cep[5:]}"
    biblioteca.endereco = endereco
    biblioteca.cidade = cidade
    biblioteca.estado = estado
    biblioteca.telefone = telefone
    endereco_mudou = endereco_anterior != (biblioteca.endereco, biblioteca.cep)
    biblioteca.horario_abertura = abertura or None
    biblioteca.horario_fechamento = fechamento or None
    biblioteca.dias_funcionamento = dias or None
    if endereco_mudou:
        biblioteca.latitude = biblioteca.longitude = None
    return biblioteca


@admin_bp.route("/bibliotecas", methods=["GET", "POST"])
@admin_required
def bibliotecas():
    if request.method == "POST":
        try:
            db.session.add(_save_biblioteca(request.form))
            db.session.commit()
            return redirect(url_for("admin.bibliotecas"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "erro")
        except Exception:
            db.session.rollback()
            flash("Não foi possível cadastrar a unidade.", "erro")
    return render_template(
        "admin/bibliotecas.html",
        bibliotecas=Biblioteca.query.order_by(
            Biblioteca.estado,
            Biblioteca.cidade,
            Biblioteca.nome,
        ).all(),
    )


@admin_bp.post("/bibliotecas/<int:biblioteca_id>/editar")
@admin_required
def editar_biblioteca(biblioteca_id):
    biblioteca = db.session.get(Biblioteca, biblioteca_id)
    if not biblioteca:
        abort(404)
    try:
        _save_biblioteca(request.form, biblioteca)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "erro")
    except Exception:
        db.session.rollback()
        flash("Não foi possível atualizar os dados da unidade.", "erro")
    return redirect(url_for("admin.bibliotecas"))


@admin_bp.post("/bibliotecas/<int:biblioteca_id>/excluir")
@admin_required
def excluir_biblioteca(biblioteca_id):
    biblioteca = db.session.get(Biblioteca, biblioteca_id)
    if not biblioteca:
        abort(404)
    if Transacao.query.filter_by(biblioteca_id=biblioteca.id).first():
        flash("Esta unidade possui pedidos no histórico e não pode ser excluída.", "erro")
    else:
        try:
            db.session.delete(biblioteca)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível excluir a unidade.", "erro")
    return redirect(url_for("admin.bibliotecas"))


@admin_bp.get("")
@admin_bp.get("/")
def admin_root():
    return redirect(url_for("admin.dashboard"))


@admin_bp.get("/dashboard")
@admin_required
def dashboard():
    total_livros, unidades = (
        db.session.query(func.count(Livro.id), func.coalesce(func.sum(Livro.estoque), 0))
        .filter(Livro.ativo.is_(True))
        .one()
    )
    vendas, faturamento = (
        db.session.query(
            func.count(Transacao.id),
            func.coalesce(func.sum(Transacao.valor_base + Transacao.frete), 0),
        )
        .filter_by(tipo="compra", pagamento_status="approved")
        .one()
    )
    rentals = Transacao.query.filter_by(
        tipo="aluguel",
        status="ativa",
        pagamento_status="approved",
    ).count()
    multas = sum(
        tx.multa if tx.status != "ativa" else tx.calcular_multa()
        for tx in Transacao.query.options(joinedload(Transacao.livro))
        .filter_by(
            tipo="aluguel",
            pagamento_status="approved",
        )
        .all()
    )
    por_status = dict(
        db.session.query(Transacao.status, func.count(Transacao.id)).group_by(Transacao.status).all()
    )
    por_genero = (
        db.session.query(Livro.genero, func.coalesce(func.sum(Livro.estoque), 0))
        .filter(Livro.ativo.is_(True))
        .group_by(Livro.genero)
        .order_by(func.sum(Livro.estoque).desc())
        .limit(6)
        .all()
    )
    hoje = date.today()
    dias = [hoje - timedelta(days=i) for i in range(13, -1, -1)]
    contagem = dict(
        db.session.query(Transacao.data_transacao, func.count(Transacao.id))
        .filter(Transacao.data_transacao >= dias[0])
        .group_by(Transacao.data_transacao)
        .all()
    )
    serie = [(d, int(contagem.get(d, 0))) for d in dias]
    sem_estoque = Livro.query.filter(Livro.ativo.is_(True), Livro.estoque <= 0).count()
    recentes = (
        Transacao.query.options(joinedload(Transacao.livro))
        .order_by(Transacao.id.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        por_status=por_status,
        por_genero=[(g, int(n)) for g, n in por_genero],
        serie=serie,
        sem_estoque=sem_estoque,
        recentes=recentes,
        total_livros=total_livros,
        unidades=int(unidades),
        clientes=Usuario.query.filter_by(papel="cliente").count(),
        faturamento=faturamento,
        vendas=vendas,
        alugueis=rentals,
        multas=multas,
        pendentes=Doacao.query.filter_by(status="Aguardando Análise").count(),
    )


@admin_bp.get("/livros")
@admin_required
def livros():
    q = request.args.get("q", "").strip()[:120]
    situacao = request.args.get("situacao", "")
    query = Livro.query
    if q:
        termo = f"%{q}%"
        query = query.filter(
            db.or_(Livro.titulo.ilike(termo), Livro.autor.ilike(termo), Livro.isbn.ilike(termo))
        )
    if situacao == "ativos":
        query = query.filter(Livro.ativo.is_(True))
    elif situacao == "inativos":
        query = query.filter(Livro.ativo.is_(False))
    elif situacao == "sem_estoque":
        query = query.filter(Livro.ativo.is_(True), Livro.estoque <= 0)
    return render_template(
        "admin/livros.html",
        livros=query.order_by(Livro.ativo.desc(), Livro.titulo).all(),
        total=Livro.query.count(),
        q=q,
        situacao=situacao,
    )


@admin_bp.route("/livros/novo", methods=["GET", "POST"])
@admin_required
def novo_livro():
    if request.method == "POST":
        try:
            db.session.add(_save_book(request.form))
            db.session.commit()
            return redirect(url_for("admin.livros"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "erro")
        except Exception:
            db.session.rollback()
            flash(
                "Não foi possível salvar. Verifique se o ISBN já está cadastrado.",
                "erro",
            )
    return render_template(
        "admin/livro_form.html", livro=None, form=request.form if request.method == "POST" else {}
    )


@admin_bp.route("/livros/<int:livro_id>/editar", methods=["GET", "POST"])
@admin_required
def editar_livro(livro_id):
    livro = db.session.get(Livro, livro_id)
    if not livro:
        abort(404)
    if request.method == "POST":
        try:
            _save_book(request.form, livro)
            db.session.commit()
            return redirect(url_for("admin.livros"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "erro")
        except Exception:
            db.session.rollback()
            flash("Não foi possível atualizar. Verifique o ISBN.", "erro")
    return render_template(
        "admin/livro_form.html", livro=livro, form=request.form if request.method == "POST" else {}
    )


@admin_bp.post("/livros/<int:livro_id>/desativar")
@admin_required
def desativar_livro(livro_id):
    livro = db.session.get(Livro, livro_id)
    if livro:
        livro.ativo = False
        db.session.commit()
    return redirect(url_for("admin.livros"))


@admin_bp.get("/transacoes")
@admin_required
def transacoes():
    q = request.args.get("q", "").strip()[:120]
    status = request.args.get("status", "")
    query = Transacao.query.options(
        joinedload(Transacao.livro), joinedload(Transacao.usuario), joinedload(Transacao.biblioteca)
    )
    if status:
        query = query.filter(Transacao.status == status)
    if q:
        termo = f"%{q}%"
        query = query.join(Livro, Transacao.livro_id == Livro.id).filter(
            db.or_(
                Transacao.nome_completo.ilike(termo),
                Transacao.email_contato.ilike(termo),
                Transacao.referencia_pedido.ilike(termo),
                Livro.titulo.ilike(termo),
            )
        )
    itens = query.order_by(Transacao.data_transacao.desc(), Transacao.id.desc()).all()
    return render_template(
        "admin/transacoes.html",
        transacoes=itens,
        total=Transacao.query.count(),
        q=q,
        status=status,
    )


@admin_bp.post("/transacoes/<int:transacao_id>/entrega")
@admin_required
def atualizar_entrega(transacao_id):
    tx = db.session.get(Transacao, transacao_id)
    status = request.form.get("status_entrega", "")
    validos = {
        "Pendente",
        "Preparando envio",
        "Aguardando retirada",
        "Enviado",
        "Disponível para retirada",
        "Retirado",
        "Entregue",
    }
    if (
        not tx
        or tx.pagamento_status != "approved"
        or tx.status
        not in (
            "ativa",
            "concluida",
            "devolvida",
        )
        or status not in validos
    ):
        flash("Transação paga e status de entrega válido são necessários.", "erro")
    else:
        tx.status_entrega = status
        db.session.commit()
    return redirect(url_for("admin.transacoes"))


@admin_bp.get("/curadoria")
@admin_required
def curadoria():
    filtro = request.args.get("status", "Aguardando Análise")
    query = Doacao.query.options(joinedload(Doacao.usuario))
    if filtro in ("Aguardando Análise", "Aprovada", "Recusada"):
        query = query.filter_by(status=filtro)
    else:
        filtro = "todas"
    contagem = dict(db.session.query(Doacao.status, func.count(Doacao.id)).group_by(Doacao.status).all())
    return render_template(
        "admin/curadoria.html",
        doacoes=query.order_by(Doacao.criada_em.asc()).all(),
        filtro=filtro,
        contagem=contagem,
    )


def _avisar_doador(doacao, aprovada):
    """Envia por e-mail o resultado da análise da doação ao doador."""
    doador = db.session.get(Usuario, doacao.usuario_id)
    if not doador or not doador.email:
        return
    if aprovada:
        assunto = f"Sua doação “{doacao.titulo}” foi aprovada"
        texto = (
            f"Olá, {doador.nome}!\n\n"
            f"Obrigado por doar “{doacao.titulo}” à Biblioteca Aberta. "
            "A obra foi aprovada e já faz parte do acervo comunitário.\n\n"
            "Obrigado por contribuir!\n"
        )
    else:
        assunto = f"Sua doação “{doacao.titulo}” não foi aceita"
        texto = (
            f"Olá, {doador.nome}!\n\n"
            f"Infelizmente não foi possível aceitar a doação de “{doacao.titulo}”.\n\n"
            f"Motivo: {doacao.justificativa}\n\n"
            "Você pode enviar outra obra quando quiser.\n"
        )
    enviar_email(doador.email, assunto, texto)


@admin_bp.post("/curadoria/<int:doacao_id>/aprovar")
@admin_required
def aprovar(doacao_id):
    doacao = db.session.get(Doacao, doacao_id)
    if not doacao or doacao.status != "Aguardando Análise":
        flash("Doação pendente não encontrada.", "erro")
        return redirect(url_for("admin.curadoria"))
    livro = Livro(
        titulo=doacao.titulo,
        autor=doacao.autor,
        editora=doacao.editora,
        ano=doacao.ano,
        isbn=doacao.isbn,
        genero="Doação",
        categoria="Acervo comunitário",
        modalidade="Aluguel",
        estoque=1,
        preco_venda=0,
        preco_aluguel=0,
        ativo=True,
        resumo="Obra incorporada por doação comunitária.",
        avaliacao=0,
    )
    doacao.status = "Aprovada"
    try:
        db.session.add(livro)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(
            "Não foi possível aprovar. Verifique se o ISBN já existe no acervo.",
            "erro",
        )
    else:
        _avisar_doador(doacao, aprovada=True)
    return redirect(url_for("admin.curadoria"))


@admin_bp.post("/curadoria/<int:doacao_id>/recusar")
@admin_required
def recusar(doacao_id):
    doacao = db.session.get(Doacao, doacao_id)
    justificativa = request.form.get("justificativa", "").strip()
    if not doacao or doacao.status != "Aguardando Análise":
        flash("Doação pendente não encontrada.", "erro")
    elif not justificativa:
        flash("Informe uma justificativa para a recusa.", "erro")
    else:
        doacao.status = "Recusada"
        doacao.justificativa = justificativa
        db.session.commit()
        _avisar_doador(doacao, aprovada=False)
    return redirect(url_for("admin.curadoria"))
