"""
Gera os ícones e a imagem de compartilhamento (sem bibliotecas externas).

Rodar:  py ferramentas/gerar-icones.py
Os arquivos saem em  static/img/ .

TROCAR: quando a logo oficial da barbearia chegar, substitua os PNGs por ela.
"""

import math
import os
import struct
import zlib

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "static", "img")

CARVAO = (17, 17, 17)
OURO = (201, 162, 75)
CREME = (245, 241, 232)
VERMELHO = (155, 44, 44)


def escrever_png(caminho, largura, altura, pixel):
    linhas = bytearray()
    for y in range(altura):
        linhas.append(0)  # filtro "none"
        for x in range(largura):
            r, g, b = pixel(x, y)
            linhas += bytes((r, g, b))

    def bloco(tipo, dados):
        return (
            struct.pack(">I", len(dados))
            + tipo
            + dados
            + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
        )

    conteudo = (
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(bytes(linhas), 9))
        + bloco(b"IEND", b"")
    )
    with open(caminho, "wb") as arquivo:
        arquivo.write(conteudo)
    print(f"ok  {os.path.relpath(caminho, RAIZ)}  ({largura}x{altura})")


def icone(tamanho):
    """Círculo dourado com um poste de barbeiro no centro."""
    centro = tamanho / 2
    raio_externo = tamanho * 0.42
    raio_interno = tamanho * 0.38
    meia_largura = tamanho * 0.075
    meia_altura = tamanho * 0.17

    def pixel(x, y):
        dx, dy = x - centro, y - centro
        distancia = math.hypot(dx, dy)

        if raio_interno <= distancia <= raio_externo:
            return OURO

        # poste central com listras diagonais
        if abs(dx) <= meia_largura and abs(dy) <= meia_altura:
            faixa = int(((x + y) / (tamanho * 0.06))) % 3
            if faixa == 0:
                return CREME
            if faixa == 1:
                return VERMELHO
            return OURO

        if distancia < raio_interno:
            return CARVAO

        return CARVAO

    return pixel


def capa():
    """Imagem 1200x630 para o Open Graph (WhatsApp, Instagram, Facebook)."""
    largura, altura = 1200, 630
    centro_x, centro_y = 260, altura / 2
    raio = 150

    def pixel(x, y):
        dx, dy = x - centro_x, y - centro_y
        distancia = math.hypot(dx, dy)
        if raio - 8 <= distancia <= raio:
            return OURO
        if distancia < raio - 8:
            faixa = int(((x + y) / 26)) % 3
            if abs(dx) < 42 and abs(dy) < 96:
                return CREME if faixa == 0 else (VERMELHO if faixa == 1 else OURO)
            return CARVAO
        # linhas douradas decorativas à direita
        if 520 < x < 1120 and abs(y - (altura / 2)) < 3:
            return OURO
        if 520 < x < 900 and abs(y - (altura / 2) + 54) < 2:
            return (90, 82, 66)
        # brilho suave no fundo
        brilho = max(0.0, 1 - math.hypot(x - 900, y - 120) / 620) * 0.16
        base = 14 + int(brilho * 40)
        return (base, base, base + 2)

    return pixel


if __name__ == "__main__":
    os.makedirs(SAIDA, exist_ok=True)
    escrever_png(os.path.join(SAIDA, "icone-192.png"), 192, 192, icone(192))
    escrever_png(os.path.join(SAIDA, "icone-512.png"), 512, 512, icone(512))
    escrever_png(os.path.join(SAIDA, "og-barbearia.png"), 1200, 630, capa())
    print("Pronto. Substitua por arte oficial quando tiver.")