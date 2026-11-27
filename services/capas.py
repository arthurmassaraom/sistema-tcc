"""Capas de livros enviadas pelo admin.

A imagem é validada pela assinatura, recortada automaticamente no formato de
capa (2:3, centralizada), reduzida para 400 x 600 e salva como JPEG novo, sem
metadados. O nome do arquivo é aleatório.
"""

import io
import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

from services.avatar import MAX_PIXELS, detectar_tipo

LIMITE_BYTES = 5 * 1024 * 1024
LARGURA, ALTURA = 400, 600
PREFIXO_ENVIADA = "books/capa-"


class CapaErro(ValueError):
    pass


def _pasta_capas():
    pasta = Path(current_app.static_folder) / "images" / "books"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def processar_capa(arquivo):
    """Retorna o caminho relativo da nova capa (ex.: 'books/capa-ab12.jpg') ou None se não houve envio."""
    if arquivo is None or not arquivo.filename:
        return None
    dados = arquivo.read(LIMITE_BYTES + 1)
    if len(dados) > LIMITE_BYTES:
        raise CapaErro("A capa deve ter no máximo 5 MB.")
    if detectar_tipo(dados[:16]) is None:
        raise CapaErro("Envie a capa em JPG, PNG ou WebP.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise CapaErro("Não foi possível ler a imagem da capa.") from exc
    imagem = ImageOps.exif_transpose(imagem).convert("RGB")
    capa = ImageOps.fit(imagem, (LARGURA, ALTURA), Image.LANCZOS, centering=(0.5, 0.5))
    nome = f"capa-{secrets.token_hex(8)}.jpg"
    capa.save(_pasta_capas() / nome, "JPEG", quality=88, optimize=True)
    return f"books/{nome}"


def remover_capa_enviada(caminho):
    """Apaga só capas enviadas pelo admin; as capas originais do acervo não são tocadas."""
    if not caminho or not caminho.startswith(PREFIXO_ENVIADA):
        return
    try:
        (Path(current_app.static_folder) / "images" / caminho).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Não foi possível remover a capa antiga: %s", caminho)
