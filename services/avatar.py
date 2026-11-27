"""Processamento seguro de fotos de perfil.

- O tipo é validado pela assinatura (bytes iniciais), não pela extensão.
- Limite de 2 MB e de dimensões, para evitar "bombas" de descompressão.
- A imagem é reorientada, recortada em quadrado, reduzida para 512 px e salva
  como JPEG novo: metadados EXIF (como localização GPS) não são copiados.
- O nome do arquivo é aleatório; o nome original nunca é usado.
"""

import io
import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError

LIMITE_BYTES = 2 * 1024 * 1024
TAMANHO_FINAL = 512
MAX_PIXELS = 40_000_000
ASSINATURAS = {
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF",),
}


class AvatarErro(ValueError):
    pass


def detectar_tipo(cabecalho):
    for tipo, assinaturas in ASSINATURAS.items():
        for assinatura in assinaturas:
            if cabecalho.startswith(assinatura):
                if tipo == "webp" and cabecalho[8:12] != b"WEBP":
                    continue
                return tipo
    return None


def pasta_avatares():
    pasta = current_app.config.get("AVATAR_DIR") or str(
        Path(current_app.static_folder) / "uploads" / "avatars"
    )
    caminho = Path(pasta)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def processar_avatar(arquivo):
    """Valida e grava a foto. Retorna o nome do arquivo salvo."""
    if not arquivo or not getattr(arquivo, "filename", ""):
        raise AvatarErro("Escolha uma imagem para enviar.")
    dados = arquivo.stream.read(LIMITE_BYTES + 1)
    if len(dados) > LIMITE_BYTES:
        raise AvatarErro("A imagem deve ter no máximo 2 MB.")
    if not dados:
        raise AvatarErro("O arquivo enviado está vazio.")
    tipo = detectar_tipo(dados[:16])
    if not tipo:
        raise AvatarErro("Envie uma imagem JPG, PNG ou WebP válida.")
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(dados)) as verificacao:
            verificacao.verify()
        imagem = Image.open(io.BytesIO(dados))
        if imagem.format and imagem.format.lower() not in ("jpeg", "png", "webp"):
            raise AvatarErro("Envie uma imagem JPG, PNG ou WebP válida.")
        if imagem.width * imagem.height > MAX_PIXELS:
            raise AvatarErro("A imagem tem dimensões grandes demais.")
        imagem = ImageOps.exif_transpose(imagem)
        imagem = ImageOps.fit(imagem.convert("RGB"), (TAMANHO_FINAL, TAMANHO_FINAL), Image.LANCZOS)
    except AvatarErro:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise AvatarErro("Não foi possível ler a imagem. Tente outro arquivo.") from exc
    nome = f"{secrets.token_hex(16)}.jpg"
    destino = pasta_avatares() / nome
    # Nova imagem sem EXIF: save() não recebe exif=, então nenhum metadado é gravado.
    imagem.save(destino, "JPEG", quality=86, optimize=True, progressive=True)
    return nome


def remover_arquivo(nome):
    if not nome or "/" in nome or "\\" in nome or nome.startswith("."):
        return
    caminho = pasta_avatares() / nome
    try:
        caminho.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Não foi possível remover um avatar antigo.")
