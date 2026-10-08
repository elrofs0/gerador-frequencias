"""Vídeo com fundo cósmico e geometria sagrada girando devagar, sobre o áudio gerado.

Renderiza só um loop curto (LOOP_S segundos) e o ffmpeg repete esse loop pela duração do
áudio sem recodificar (-stream_loop + -c:v copy): rápido mesmo para 30 minutos.
Sem piscadas: só rotação lenta e um "respirar" de 10 s (seguro para fotossensíveis).
"""
import io
import math
import os
import shutil
import subprocess
import tempfile

import numpy as np
import wave

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FFMPEG = shutil.which("ffmpeg")
W, H, FPS, LOOP_S = 1280, 720, 15, 20  # giro lento: 15 fps já fica suave
S = 720  # tamanho da camada do símbolo (altura toda do vídeo)
OURO = (232, 190, 92)

SIMBOLOS = {"🌸 Flor da Vida": "flor", "✡ Cubo de Metatron": "metatron",
            "✴ Merkabá": "merkaba", "🪷 Mandala de Lótus": "lotus"}
SIMETRIA = {"flor": 6, "metatron": 6, "merkaba": 6, "lotus": 8}  # giro por loop = 360/simetria


def _hex(n_aneis, passo):
    """Centros de uma grade hexagonal com `n_aneis` anéis em volta do centro."""
    pts = []
    for q in range(-n_aneis, n_aneis + 1):
        for r in range(-n_aneis, n_aneis + 1):
            if abs(q + r) <= n_aneis:
                pts.append((passo * (q + r / 2), passo * r * math.sqrt(3) / 2))
    return pts


def _desenhar(nome, tam):
    """Símbolo em linhas douradas sobre preto (RGB), desenhado em `tam` px."""
    img = Image.new("RGB", (tam, tam))
    d = ImageDraw.Draw(img)
    c, lw = tam / 2, max(2, tam // 300)

    def circ(x, y, r):
        d.ellipse((c + x - r, c + y - r, c + x + r, c + y + r), outline=OURO, width=lw)

    def linha(p, q):
        d.line((c + p[0], c + p[1], c + q[0], c + q[1]), fill=OURO, width=lw)

    R = tam * 0.40  # margem para o brilho não ser cortado na borda da camada
    if nome == "flor":
        r = R / 3
        for x, y in _hex(2, r):
            circ(x, y, r)
        circ(0, 0, R)
        circ(0, 0, R + lw * 3)
    elif nome == "metatron":
        r = R / 5
        centros = [(0, 0)] + [(k * 2 * r * math.cos(a), k * 2 * r * math.sin(a))
                              for k in (1, 2) for a in (math.pi / 3 * i + math.pi / 6 for i in range(6))]
        for i, p in enumerate(centros):
            for q in centros[i + 1:]:
                linha(p, q)
        for x, y in centros:
            circ(x, y, r)
    elif nome == "merkaba":
        for raio in (R, R * 0.5, R * 0.25):  # estrelas de Davi concêntricas
            for desloc in (0, math.pi):
                tri = [(raio * math.cos(a), raio * math.sin(a))
                       for a in (desloc - math.pi / 2 + 2 * math.pi / 3 * i for i in range(3))]
                for i in range(3):
                    linha(tri[i], tri[(i + 1) % 3])
            circ(0, 0, raio)
    else:  # lótus: anéis de círculos sobrepostos formam pétalas
        for n, dist, raio in ((8, 0.18, 0.18), (16, 0.45, 0.24), (32, 0.75, 0.18)):
            for i in range(n):
                a = 2 * math.pi * i / n
                circ(R * dist * math.cos(a), R * dist * math.sin(a), R * raio)
        circ(0, 0, R)
        circ(0, 0, R * 0.08)
    return img


def _camadas(nome):
    """Símbolo nítido + brilho (desfocado), supersample 2x para linhas suaves."""
    nitido = _desenhar(nome, S * 2).resize((S, S), Image.LANCZOS)
    brilho = nitido.resize((S // 2, S // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(7))
    return nitido, brilho  # brilho em meia resolução: girar fica 4x mais barato


def _fundo(rng):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    dist = np.hypot((x - W / 2) / W, (y - H / 2) / H)
    centro, borda = np.array([58, 24, 104], np.float32), np.array([8, 4, 24], np.float32)
    fundo = centro + (borda - centro) * np.clip(dist / 0.7, 0, 1)[..., None]
    n = 260
    estrelas = (rng.integers(0, H, n), rng.integers(0, W, n), rng.uniform(80, 255, n),
                rng.uniform(0, 2 * np.pi, n))
    return fundo, estrelas


def _texto(legenda):
    """Legenda e assinatura numa camada RGB aditiva."""
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    fonte, pequena = ImageFont.load_default(size=34), ImageFont.load_default(size=18)
    d.text((W / 2, H - 46), legenda, font=fonte, fill=OURO, anchor="mm")
    d.text((W - 20, H - 18), "feito por Elrofs", font=pequena, fill=(160, 122, 31), anchor="rs")
    return np.asarray(img, np.float32)


def _ceu(fundo, estrelas, texto, fase):
    """Fundo + estrelas (brilho de cada uma depende da fase) + texto, já em uint8."""
    ey, ex, eb, ef = estrelas
    ceu = fundo.copy()
    ceu[ey, ex] += (eb * (0.55 + 0.45 * np.sin(ef + fase)))[:, None]
    return Image.fromarray(np.clip(ceu + texto, 0, 255).astype(np.uint8))


def _lut(fator):
    return [min(255, int(v * fator)) for v in range(256)] * 3


def _quadros(nome, legenda):
    rng = np.random.default_rng(7)
    nitido, brilho = _camadas(nome)
    fundo, estrelas = _fundo(rng)
    texto = _texto(legenda)
    # cintilar = mistura entre dois céus com fases opostas (operações em C do Pillow: rápido)
    ceu_a, ceu_b = (_ceu(fundo, estrelas, texto, fase) for fase in (0, np.pi))
    giro_loop = 360 / SIMETRIA[nome]
    caixa = ((W - S) // 2, (H - S) // 2, (W + S) // 2, (H + S) // 2)
    for f in range(FPS * LOOP_S):
        t = f / FPS  # tudo periódico em LOOP_S: emenda perfeita
        respira = 0.75 + 0.25 * math.sin(2 * math.pi * t / 10)
        ang = -giro_loop * t / LOOP_S
        simbolo = ImageChops.add(nitido.rotate(ang, Image.BILINEAR).point(_lut(0.7 + 0.3 * respira)),
                                 brilho.rotate(ang, Image.BILINEAR).resize((S, S), Image.BILINEAR)
                                 .point(_lut(2.2 * respira)))
        quadro = Image.blend(ceu_a, ceu_b, 0.5 + 0.5 * math.sin(4 * math.pi * t / LOOP_S))
        quadro.paste(ImageChops.add(quadro.crop(caixa), simbolo), caixa)
        yield quadro.tobytes()


def gerar_video(wav: bytes, simbolo: str, legenda: str) -> bytes:
    """MP4 (H.264 + AAC) com a duração do áudio. Usa uma pasta temporária apagada no fim."""
    with tempfile.TemporaryDirectory() as tmp:
        loop, audio, saida = (os.path.join(tmp, n) for n in ("loop.mp4", "audio.wav", "saida.mp4"))
        with open(audio, "wb") as f:
            f.write(wav)
        enc = subprocess.Popen([FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                                "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
                                "-g", str(FPS * 2), loop], stdin=subprocess.PIPE)
        for q in _quadros(simbolo, legenda):
            enc.stdin.write(q)
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("ffmpeg falhou ao gerar o loop de vídeo")
        with wave.open(io.BytesIO(wav)) as wf:
            duracao = wf.getnframes() / wf.getframerate()
        subprocess.run([FFMPEG, "-y", "-v", "error", "-stream_loop", "-1", "-i", loop, "-i", audio,
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                        "-t", f"{duracao:.3f}", "-movflags", "+faststart", saida], check=True)
        with open(saida, "rb") as f:
            return f.read()


if __name__ == "__main__":
    # Prévia de cada símbolo: `python video.py` grava previa_<nome>.png na pasta atual
    for rotulo, nome in SIMBOLOS.items():
        q = next(_quadros(nome, "528 Hz"))
        Image.frombytes("RGB", (W, H), q).save(f"previa_{nome}.png")
        print("ok", nome)
