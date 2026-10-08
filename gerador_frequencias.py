"""Gerador de Frequências Terapêuticas e Tons Puros — rode com: streamlit run gerador_frequencias.py"""
import io
import json
import math
import os
import struct
import wave
from array import array
from fractions import Fraction

import numpy as np  # já vem com o Streamlit; usado só nas camadas de ambiente
import streamlit as st
import streamlit.components.v1 as components

from video import FFMPEG, SIMBOLOS, gerar_video, gerar_video_faixas

RATE = 44100
AMP = 0.8 * 32767  # headroom de ~2 dB, evita clipping
FADE = int(RATE * 0.05)  # 50 ms de fade in/out para não estalar

# Streamlit Community Cloud roda os apps a partir de /mount/src (≈1 GB de RAM): limita o download.
NUVEM = os.path.abspath(__file__).startswith("/mount/src/")
LIMITE_MIN = 10 if NUVEM else 30
LIMITE_VIDEO_MIN = 30 if NUVEM else 24 * 60  # vídeo da playlist: gerado faixa a faixa, cabe mais

AMBIENTES = {"🌧 Chuva (gravação real)": "chuva-real", "🌊 Mar (gravação real)": "mar-real",
             "🐦 Pássaros (gravação real)": "passaros", "💧 Riacho (gravação real)": "riacho",
             "🔥 Fogueira (gravação real)": "fogueira",
             "🌧 Chuva (sintética)": "chuva", "🌊 Ondas (sintéticas)": "ondas",
             "🍃 Vento (sintético)": "vento", "🎹 Melodia ambiente": "melodia"}
# Gravações do Wikimedia Commons (CC0/domínio público; fogueira CC BY 3.0, créditos no README
# e no rodapé), em loops sem emenda.
PASTA_SONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
GRAVACOES = {"chuva-real": "chuva", "mar-real": "mar", "passaros": "passaros", "riacho": "riacho",
             "fogueira": "fogueira"}
AMB_SEG = 64  # o ambiente é um loop de 64 s, contínuo nas emendas
ACORDES = [(1, 5 / 4, 3 / 2), (5 / 6, 1, 5 / 4), (2 / 3, 5 / 6, 1), (3 / 4, 15 / 16, 9 / 8)]  # I vi IV V
SINOS = (2, 9 / 4, 5 / 2, 3, 10 / 3)  # pentatônica acima da raiz

PRESETS = {
    "4.5 Hz — Theta profundo: meditação, introspecção": 4.5,
    "7.83 Hz — Ressonância Schumann: aterramento, calma": 7.83,
    "10 Hz — Alpha: relaxamento alerta, foco leve": 10.0,
    "174 Hz — Solfeggio: alívio de tensão, segurança": 174.0,
    "285 Hz — Solfeggio: restauração, bem-estar": 285.0,
    "528 Hz — Solfeggio: harmonia, 'frequência do amor'": 528.0,
}


def raiz_musical(f: float) -> float:
    """Dobra/divide a frequência em oitavas até 110–220 Hz: a melodia fica afinada com o tom."""
    while f < 110:
        f *= 2
    while f >= 220:
        f /= 2
    return f


def ambiente(nomes: list[str], raiz: float) -> np.ndarray:
    """Loop estéreo de AMB_SEG s (float32, pico 1). Ruídos filtrados por FFT são periódicos,
    então o loop emenda sem clique."""
    rng = np.random.default_rng()
    n = RATE * AMB_SEG
    t = np.arange(n, dtype=np.float32) / RATE
    f = np.fft.rfftfreq(n, 1 / RATE)

    def ruido(forma):
        x = np.fft.irfft(np.fft.rfft(rng.standard_normal((n, 2)), axis=0) * forma[:, None], n, axis=0)
        return (x / np.abs(x).max()).astype(np.float32)

    def onda(periodo, fase=0.0):  # 0..1, período divide AMB_SEG
        return (0.5 + 0.5 * np.sin(2 * np.pi * t / periodo + fase))[:, None]

    camadas = {
        "chuva": lambda: 0.5 * ruido((f / (f + 700)) ** 2 / np.sqrt(f + 1) * np.exp(-f / 10000)),
        "ondas": lambda: 0.8 * ruido(1 / (f + 40) * (f < 1200))
                 * np.hstack([onda(8), onda(8, 0.6)]) ** 3,
        "vento": lambda: 0.7 * (ruido(np.exp(-((f - 350) / 150) ** 2)) * (0.3 + 0.7 * onda(16))
                                + 0.5 * ruido(np.exp(-((f - 900) / 400) ** 2)) * (1 - onda(16)))
                 * (0.5 + 0.5 * onda(32, 1.0)),
        "melodia": lambda: 0.6 * melodia(raiz, rng),
    }
    out = sum(camadas[nome]() for nome in nomes)
    return out / np.abs(out).max()


@st.cache_data
def gravacao(nome: str) -> np.ndarray:
    with wave.open(os.path.join(PASTA_SONS, GRAVACOES[nome] + ".wav")) as wf:
        x = np.frombuffer(wf.readframes(wf.getnframes()), "<i2").astype(np.float32) / 32767
    return 1.5 * np.stack([x, np.roll(x, len(x) // 2)], axis=1)  # direito defasado = estéreo amplo


def melodia(raiz: float, rng) -> np.ndarray:
    n_ac = RATE * 16  # 4 acordes de 16 s = 64 s
    tl = np.arange(n_ac, dtype=np.float32) / RATE
    env = np.sin(np.pi * tl / 16) ** 2  # sobe e desce: zero nas emendas
    pad = np.zeros((RATE * AMB_SEG, 2), np.float32)
    for k, acorde in enumerate(ACORDES):
        for r in acorde:
            for c, det in ((0, 1.0), (1, 1.003)):  # leve desafinação L/R = amplitude estéreo
                fr = raiz * r * det
                pad[k * n_ac:(k + 1) * n_ac, c] += env * (np.sin(2 * np.pi * fr * tl)
                                                          + 0.3 * np.sin(4 * np.pi * fr * tl))
    pad /= np.abs(pad).max()
    nb = RATE * 4  # um sino a cada 4 s
    tb = tl[:nb]
    env_b = np.exp(-tb * 1.2) * (1 - np.exp(-tb * 200)) * (1 - (tb / 4) ** 8)
    for j in range(AMB_SEG // 4):
        nota = np.sin(2 * np.pi * raiz * rng.choice(SINOS) * tb) * env_b
        pan = rng.uniform(0.2, 0.8)
        pad[j * nb:(j + 1) * nb] += 0.35 * nota[:, None] * np.array([1 - pan, pan], np.float32)
    return pad


def gerar_wav(freqs: list[float], segundos: int, ambientes=(), vol_freq=1.0) -> bytes:
    """Uma frequência por canal: [f] = mono, [esq, dir] = estéreo (binaural).
    Com `ambientes`, mistura as camadas por cima e a frequência fica ao fundo (`vol_freq`)."""
    # Um bloco de `den` segundos contém um número inteiro de ciclos em todos os canais
    # (ex.: 7.83 Hz -> 100 s), então repeti-lo é contínuo: senoide pura sem salto de fase.
    den = math.lcm(*(Fraction(f).limit_denominator(100).denominator for f in freqs))
    bloco_n = RATE * min(den, segundos)
    total = RATE * segundos
    ch = len(freqs)

    amostras = array("h", bytes(2 * total * ch))
    for c, f in enumerate(freqs):
        w = 2 * math.pi * f / RATE
        bloco = array("h", (round(AMP * math.sin(w * i)) for i in range(bloco_n)))
        canal = bloco * (total // bloco_n + 1)
        del canal[total:]
        amostras[c::ch] = canal  # intercala L/R

    for i in range(min(FADE, total // 2) * ch):
        g = (i // ch) / FADE
        amostras[i] = round(amostras[i] * g)
        amostras[-1 - i] = round(amostras[-1 - i] * g)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        if not ambientes:
            if struct.pack("=h", 1) != struct.pack("<h", 1):  # WAV é little-endian
                amostras.byteswap()
            wf.setnchannels(ch)
            wf.writeframes(amostras.tobytes())
        else:
            wf.setnchannels(2)
            tom = np.frombuffer(amostras, np.int16).reshape(-1, ch)
            sinteticos = [a for a in ambientes if a not in GRAVACOES]
            camadas = [ambiente(sinteticos, raiz_musical(freqs[0]))] if sinteticos else []
            camadas += [gravacao(a) for a in ambientes if a in GRAVACOES]
            escala = 1 / max(1.0, 0.8 * vol_freq + 0.8)  # pico máximo possível da soma
            rampa = 3 * RATE  # fade de 3 s no ambiente
            bloco = RATE * AMB_SEG
            for i0 in range(0, total, bloco):  # bloco a bloco: pouca memória extra
                idx = np.arange(i0, min(total, i0 + bloco))
                tb = tom[idx].astype(np.float32) / 32767
                amb = np.tanh(sum(c[idx % len(c)] for c in camadas))  # cada loop no seu tamanho; tanh = limitador suave
                g = np.minimum(1, np.minimum(idx, total - idx) / rampa)[:, None]
                mix = (tb * vol_freq + 0.8 * amb * g) * escala
                wf.writeframes((mix * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def main():
    st.set_page_config(page_title="Gerador de Frequências", page_icon="✨", layout="centered")
    st.markdown(
        """<style>
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&display=swap');
        .stApp {
            background:
                radial-gradient(ellipse at top, #fff6dc 0%, transparent 55%),
                radial-gradient(ellipse at bottom, #e6d6fb 0%, transparent 60%),
                #fbf8ff;
        }
        header[data-testid="stHeader"] {background:transparent;}
        .block-container {max-width:680px; padding:3rem 1.5rem 4rem;}
        .topo {text-align:center; margin-bottom:1.5rem;}
        .topo .sol {font-size:2.4rem; line-height:1;
                    filter:drop-shadow(0 0 14px rgba(232,185,74,.7));}
        .topo h1 {font-family:'Cormorant Garamond', serif; font-weight:600;
                  font-size:clamp(2.1rem, 7vw, 3.2rem); line-height:1.1; margin:.4rem 0 .3rem;
                  background:linear-gradient(90deg, #6a3fc8, #a35bd9 50%, #d19a2a);
                  -webkit-background-clip:text; background-clip:text; color:transparent;}
        .topo p {color:#6b5a8a; margin:0; font-size:1rem;}
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background:rgba(255,255,255,.75); border-radius:20px !important;
            border:1px solid #e4d6f7 !important;
            box-shadow:0 10px 40px -12px rgba(123,79,214,.25);
        }
        .stButton button[kind="primary"] {
            background:linear-gradient(90deg, #7b4fd6, #a35bd9); border:none;
            border-radius:999px; padding:.7rem 0; font-weight:600; letter-spacing:.03em;
            box-shadow:0 6px 20px -6px rgba(123,79,214,.6);
        }
        .stDownloadButton button {border-radius:999px; border-color:#d9b65c; color:#8a6414;}
        .marca {position:fixed; bottom:12px; right:16px; z-index:999;
                font-size:.8rem; letter-spacing:.08em; opacity:.6;
                color:#a07a1f; pointer-events:none; user-select:none;}
        [class*="st-key-faixa"] [data-testid="stHorizontalBlock"] {flex-wrap:nowrap; gap:.5rem;}
        [class*="st-key-faixa"] [data-testid="stColumn"]:first-child {flex:1 1 auto; min-width:0; width:auto;}
        [class*="st-key-faixa"] [data-testid="stColumn"]:last-child {flex:0 0 auto; width:auto; min-width:0;}
        @media (max-width:640px) {
            .block-container {padding:1.5rem .75rem 4rem;}
            .marca {right:50%; transform:translateX(50%);}
        }
        </style>""",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="marca">✦ feito por Elrofs</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="topo"><div class="sol">✨</div><h1>Gerador de Frequências</h1>'
        "<p>Tons puros e batidas binaurais para relaxar, meditar e recomeçar</p></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        controles()
    if st.session_state.get("playlist"):
        with st.container(border=True):
            playlist()
    st.caption("Senoide pura · 16-bit · 44.1 kHz · Som de fogueira: “Campfire sound ambience”, "
               "Glaneur de sons, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), via Wikimedia Commons")


def controles():
    preset = st.selectbox("Escolha uma frequência", list(PRESETS) + ["Personalizada"])
    if preset == "Personalizada":
        freq = st.number_input("Frequência (Hz)", min_value=0.1, max_value=22000.0,
                               value=432.0, step=0.01, format="%.2f")
    else:
        freq = PRESETS[preset]

    minutos = st.slider("Duração (minutos)", 1, 30, 10)

    # Batida binaural só faz sentido para frequências baixas (< 40 Hz); acima disso, tom puro.
    binaural = freq < 40 and st.toggle("Modo binaural (estéreo, use fones)", value=freq < 20)
    if binaural:
        portadora = st.number_input("Portadora (Hz)", min_value=20.0, max_value=1000.0,
                                    value=200.0, step=1.0, format="%.2f")
        freqs = [portadora, portadora + freq]
        st.caption(f"Esquerdo {portadora:g} Hz · Direito {portadora + freq:g} Hz → "
                   f"o cérebro percebe uma batida de {freq:g} Hz")
        nome = f"binaural_{freq:g}Hz_portadora{portadora:g}_{minutos}min.wav"
    else:
        freqs = [freq]
        nome = f"tom_{freq:g}Hz_{minutos}min.wav"
        if freq < 20:
            st.info("Abaixo de 20 Hz o tom puro é praticamente inaudível. Ative o modo binaural.")

    escolhidos = st.multiselect("Sons de fundo (opcional)", list(AMBIENTES),
                                placeholder="Chuva, ondas, vento, melodia...")
    ambientes = [AMBIENTES[a] for a in escolhidos]
    vol_freq = 1.0
    if ambientes:
        vol_freq = st.slider("Volume da frequência", 5, 100, 30, format="%d%%") / 100
        st.caption("A frequência fica ao fundo; a melodia é afinada no mesmo tom dela.")
        nome = nome.replace(".wav", "_" + "-".join(ambientes) + ".wav")

    col1, col2 = st.columns(2)
    longo = minutos > LIMITE_MIN
    if col1.button("Gerar áudio", type="primary", use_container_width=True, disabled=longo):
        with st.spinner(f"Gerando {minutos} min..."):
            legenda = f"{freq:g} Hz" + (" · binaural" if binaural else "")
            st.session_state.audio = (gerar_wav(freqs, minutos * 60, ambientes, vol_freq), nome, legenda)
            st.session_state.pop("video", None)
    if col2.button("＋ Adicionar à playlist", use_container_width=True):
        titulo = (f"{freq:g} Hz binaural (portadora {freqs[0]:g} Hz)" if binaural
                  else f"{freq:g} Hz") + "".join(f" + {a}" for a in escolhidos) + f" · {minutos} min"
        st.session_state.setdefault("playlist", []).append(
            {"titulo": titulo, "freqs": freqs, "seg": minutos * 60, "amb": ambientes,
             "vol": vol_freq, "raiz": raiz_musical(freqs[0]),
             "legenda": f"{freq:g} Hz" + (" · binaural" if binaural else "")})
    if longo:
        st.caption(f"No site, o download vai até {LIMITE_MIN} min. "
                   "Na playlist pode usar qualquer duração, ela toca direto no navegador.")

    if "audio" in st.session_state:
        dados, nome, legenda = st.session_state.audio
        st.audio(dados, format="audio/wav")
        st.download_button("⬇ Baixar " + nome, dados, file_name=nome,
                           mime="audio/wav", use_container_width=True)
        st.caption(f"{len(dados) / 1e6:.1f} MB")

        if FFMPEG:
            with st.expander("🎬 Criar vídeo com este áudio"):
                simbolo = st.selectbox("Símbolo", list(SIMBOLOS))
                st.caption("Fundo cósmico com o símbolo girando devagar. Sem piscadas.")
                if st.button("Gerar vídeo", use_container_width=True):
                    with st.spinner("Criando o vídeo... (leva alguns segundos)"):
                        mp4 = gerar_video(dados, SIMBOLOS[simbolo], legenda)
                        st.session_state.video = (mp4, nome.replace(".wav", f"_{SIMBOLOS[simbolo]}.mp4"))
        if "video" in st.session_state:
            mp4, nome_mp4 = st.session_state.video
            st.video(mp4)
            st.download_button("⬇ Baixar vídeo " + nome_mp4, mp4, file_name=nome_mp4,
                               mime="video/mp4", use_container_width=True)
            st.caption(f"{len(mp4) / 1e6:.1f} MB")


# Player da playlist: gera as senoides ao vivo no navegador (Web Audio), sem arquivos.
# A troca de faixa é agendada no relógio de áudio (onended), então continua tocando
# mesmo com a aba em segundo plano.
PLAYER_HTML = """
<style>
  body {margin:0; font-family:'Source Sans Pro',sans-serif; color:#2e1f4a;}
  .p {display:flex; align-items:center; gap:12px; flex-wrap:wrap;}
  button {border:none; border-radius:999px; padding:10px 22px; font-size:15px; font-weight:600;
          cursor:pointer; color:#fff; background:linear-gradient(90deg,#7b4fd6,#a35bd9);}
  button.sec {background:#f1e9fc; color:#7b4fd6;}
  label {font-size:14px; display:flex; align-items:center; gap:6px;}
  .agora {margin:12px 0 6px; font-size:15px; min-height:20px;}
  .barra {height:6px; border-radius:6px; background:#ece2fa; overflow:hidden;}
  .barra div {height:100%; width:0; background:linear-gradient(90deg,#7b4fd6,#d19a2a);}
  #tela {width:100%; aspect-ratio:16/9; display:block; border-radius:14px; background:#0b0620; margin-bottom:12px;}
  #tela:fullscreen {border-radius:0;}
  select {border:1px solid #e4d6f7; border-radius:999px; padding:8px 12px; background:#fff; color:#2e1f4a; font-size:14px;}
</style>
<canvas id="tela" width="1280" height="720"></canvas>
<div class="p">
  <button id="play">▶ Tocar playlist</button>
  <button id="stop" class="sec">■ Parar</button>
  <button id="cheia" class="sec">⛶ Tela cheia</button>
  <select id="visual">
    <option value="alternar">🔄 Alternar símbolos</option>
    <option value="flor">🌸 Flor da Vida</option>
    <option value="metatron">✡ Metatron</option>
    <option value="merkaba">✴ Merkabá</option>
    <option value="lotus">🪷 Lótus</option>
  </select>
  <label><input type="checkbox" id="loop" checked> Repetir</label>
</div>
<div class="agora" id="agora"></div>
<div class="barra"><div id="prog"></div></div>
<script>
const LISTA = __LISTA__, VOL = 0.5, FADE = 1.5;
let ctx, atual = null, idx = 0, inicio = 0;
const $ = id => document.getElementById(id);

function tocar(i) {
  parar();
  if (i >= LISTA.length) { if (!$("loop").checked) return; i = 0; }
  idx = i; const it = LISTA[i], t = ctx.currentTime, fim = t + it.seg;
  const g = ctx.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(VOL, t + FADE);
  g.gain.setValueAtTime(VOL, fim - FADE);
  g.gain.linearRampToValueAtTime(0, fim);
  g.connect(saida);
  const amb = it.amb || [], vol = it.vol ?? 1;
  const escala = 1 / Math.max(1, 0.8 * vol + (amb.length ? 0.8 : 0));
  const gTom = ganho(0.8 * vol * escala), gAmb = ganho(0.8 * escala);
  gTom.connect(g); gAmb.connect(ctx.createDynamicsCompressor()).connect(g);  // limitador do ambiente
  const oscs = it.freqs.map((f, c) => {
    const o = ctx.createOscillator(); o.frequency.value = f;
    if (it.freqs.length === 2) {  // binaural: um tom em cada ouvido
      const p = ctx.createStereoPanner(); p.pan.value = c ? 1 : -1; o.connect(p); p.connect(gTom);
    } else o.connect(gTom);
    o.start(t); o.stop(fim); return o;
  });
  amb.forEach(nome => oscs.push(...CAMADAS[nome](it, gAmb, t, fim)));
  oscs[0].onended = () => tocar(idx + 1);
  atual = {g, oscs}; inicio = t;
  $("agora").textContent = `♪ ${i + 1}/${LISTA.length} — ${it.titulo}`;
  VIS.faixa(i, it.legenda || it.titulo.split(" · ")[0]);
}

// Camadas de ambiente (mesma receita do download, em Web Audio). Cada uma devolve
// as fontes que agendou, para poderem ser paradas.
const ACORDES = __ACORDES__, SINOS = __SINOS__;
const ganho = v => { const g = ctx.createGain(); g.gain.value = v; return g; };
const filtro = (tipo, f, q = 0.7) => {
  const b = ctx.createBiquadFilter(); b.type = tipo; b.frequency.value = f; b.Q.value = q; return b;
};
function ruido(t, fim) {
  const b = ctx.createBuffer(2, ctx.sampleRate * 8, ctx.sampleRate);
  for (let c = 0; c < 2; c++) { const d = b.getChannelData(c); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1; }
  const s = ctx.createBufferSource(); s.buffer = b; s.loop = true; s.start(t); s.stop(fim); return s;
}
function lfo(freq, prof, param, t, fim) {
  const o = ctx.createOscillator(), g = ganho(prof); o.frequency.value = freq; o.connect(g); g.connect(param);
  o.start(t); o.stop(fim); return o;
}
const CAMADAS = {
  chuva(it, dest, t, fim) {
    const s = ruido(t, fim); s.connect(filtro("highpass", 900)).connect(filtro("lowpass", 8000)).connect(ganho(0.35)).connect(dest);
    return [s];
  },
  ondas(it, dest, t, fim) {
    const s = ruido(t, fim), g = ganho(0.5);
    s.connect(filtro("lowpass", 450)).connect(g).connect(dest);
    return [s, lfo(1 / 8, 0.48, g.gain, t, fim)];
  },
  vento(it, dest, t, fim) {
    const s = ruido(t, fim), bp = filtro("bandpass", 500, 1.5), g = ganho(0.6);
    s.connect(bp).connect(g).connect(dest);
    return [s, lfo(1 / 16, 300, bp.frequency, t, fim), lfo(1 / 32, 0.35, g.gain, t, fim)];
  },
  melodia(it, dest, t, fim) {
    const fontes = [];
    for (let k = 0, ti = t; ti < fim; k++, ti += 16) {
      for (const r of ACORDES[k % 4]) [-0.6, 0.6].forEach((pan, c) => {
        const o = ctx.createOscillator(), g = ctx.createGain(), p = ctx.createStereoPanner();
        o.frequency.value = it.raiz * r * (c ? 1.003 : 1); p.pan.value = pan;
        g.gain.setValueAtTime(0, ti); g.gain.linearRampToValueAtTime(0.06, ti + 8); g.gain.linearRampToValueAtTime(0, ti + 16);
        o.connect(g).connect(p).connect(dest); o.start(ti); o.stop(Math.min(ti + 16, fim)); fontes.push(o);
      });
      for (let j = 0; j < 4 && ti + j * 4 < fim; j++) {
        const tb = ti + j * 4, o = ctx.createOscillator(), g = ctx.createGain(), p = ctx.createStereoPanner();
        o.frequency.value = it.raiz * SINOS[Math.floor(Math.random() * SINOS.length)]; p.pan.value = Math.random() * 1.2 - 0.6;
        g.gain.setValueAtTime(0, tb); g.gain.linearRampToValueAtTime(0.12, tb + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, tb + 3.9);
        o.connect(g).connect(p).connect(dest); o.start(tb); o.stop(Math.min(tb + 4, fim)); fontes.push(o);
      }
    }
    return fontes;
  },
};

// Gravações reais: baixadas uma vez de app/static e tocadas em loop; o canal direito
// começa no meio do loop (mesmo truque de estéreo do download).
const GRAVACOES = __GRAVACOES__, BUF = {};
async function carregar(nomes) {
  await Promise.all(nomes.filter(n => GRAVACOES[n] && !BUF[n]).map(async n => {
    const r = await fetch(new URL(`app/static/${GRAVACOES[n]}.wav`, document.baseURI));
    BUF[n] = await ctx.decodeAudioData(await r.arrayBuffer());
  }));
}
for (const n in GRAVACOES) CAMADAS[n] = (it, dest, t, fim) => [-1, 1].map((pan, c) => {
  const s = ctx.createBufferSource(), p = ctx.createStereoPanner();
  s.buffer = BUF[n]; s.loop = true; p.pan.value = pan;
  s.connect(p).connect(ganho(1.5)).connect(dest);
  s.start(t, c * BUF[n].duration / 2); s.stop(fim); return s;
});

function parar() {
  if (!atual) return;
  atual.oscs[0].onended = null;
  atual.oscs.forEach(o => { try { o.stop(); } catch (e) {} });
  atual.g.disconnect(); atual = null;
}

let saida, analisador;
$("play").onclick = async () => {
  if (!ctx) {
    ctx = new AudioContext();
    analisador = ctx.createAnalyser(); analisador.fftSize = 2048;
    saida = ctx.createGain(); saida.connect(analisador); analisador.connect(ctx.destination);
  }
  ctx.resume();
  $("agora").textContent = "Carregando sons...";
  try { await carregar(LISTA.flatMap(it => it.amb || [])); }
  catch (e) { $("agora").textContent = "Não foi possível carregar as gravações."; return; }
  tocar(0);
};
$("stop").onclick = () => { parar(); $("agora").textContent = ""; $("prog").style.width = 0; VIS.faixa(-1, ""); };
setInterval(() => {
  if (atual) $("prog").style.width = Math.min(100, (ctx.currentTime - inicio) / LISTA[idx].seg * 100) + "%";
}, 500);

// ---------- Visualização ao vivo (estilo Windows Media Player) ----------
// Céu cósmico + geometria sagrada dourada girando devagar. Reage ao volume do som, mas com
// suavização de ~2 s: nada pisca (seguro para fotossensíveis, mesmo com batidas binaurais).
const VIS = (() => {
  const tela = $("tela"), c = tela.getContext("2d"), W = tela.width, H = tela.height;
  const ORDEM = ["flor", "metatron", "merkaba", "lotus"], S = 640, OURO = "#e8be5c";
  const estrelas = Array.from({length: 220}, () => [Math.random() * W, Math.random() * H,
                                                    0.3 + Math.random() * 0.7, Math.random() * 6.28]);
  const cache = {};

  function simbolo(nome) {  // desenhado uma vez num canvas fora da tela, com brilho
    if (cache[nome]) return cache[nome];
    const cv = document.createElement("canvas"); cv.width = cv.height = S;
    const d = cv.getContext("2d"), R = S * 0.40, m = S / 2;
    d.translate(m, m); d.strokeStyle = OURO; d.lineWidth = 2.2; d.shadowColor = "#ffcf6b"; d.shadowBlur = 14;
    const circ = (x, y, r) => { d.beginPath(); d.arc(x, y, r, 0, 6.2832); d.stroke(); };
    const linha = (p, q) => { d.beginPath(); d.moveTo(p[0], p[1]); d.lineTo(q[0], q[1]); d.stroke(); };
    if (nome === "flor") {
      const r = R / 3;
      for (let q = -2; q <= 2; q++) for (let s = -2; s <= 2; s++)
        if (Math.abs(q + s) <= 2) circ(r * (q + s / 2), r * s * Math.sqrt(3) / 2, r);
      circ(0, 0, R); circ(0, 0, R + 6);
    } else if (nome === "metatron") {
      const r = R / 5, cs = [[0, 0]];
      for (const k of [1, 2]) for (let i = 0; i < 6; i++) {
        const a = Math.PI / 3 * i + Math.PI / 6; cs.push([k * 2 * r * Math.cos(a), k * 2 * r * Math.sin(a)]);
      }
      cs.forEach((p, i) => cs.slice(i + 1).forEach(q => linha(p, q)));
      cs.forEach(([x, y]) => circ(x, y, r));
    } else if (nome === "merkaba") {
      for (const raio of [R, R / 2, R / 4]) {
        for (const desl of [0, Math.PI]) {
          const tri = [0, 1, 2].map(i => { const a = desl - Math.PI / 2 + 2 * Math.PI / 3 * i;
                                           return [raio * Math.cos(a), raio * Math.sin(a)]; });
          tri.forEach((p, i) => linha(p, tri[(i + 1) % 3]));
        }
        circ(0, 0, raio);
      }
    } else {
      for (const [n, dist, raio] of [[8, .18, .18], [16, .45, .24], [32, .75, .18]])
        for (let i = 0; i < n; i++) { const a = 2 * Math.PI * i / n; circ(R * dist * Math.cos(a), R * dist * Math.sin(a), R * raio); }
      circ(0, 0, R); circ(0, 0, R * 0.08);
    }
    return cache[nome] = cv;
  }

  let atualSim = "flor", anterior = null, troca = 0, legenda = "", nivel = 0, giro = 0, ultimo = performance.now();
  const dados = new Float32Array(2048);

  function escolher(i) {
    const v = $("visual").value;
    return v === "alternar" ? ORDEM[Math.max(i, 0) % ORDEM.length] : v;
  }
  $("visual").onchange = () => faixa(idx, legenda);

  function faixa(i, texto) {
    const novo = escolher(i);
    if (novo !== atualSim) { anterior = atualSim; atualSim = novo; troca = performance.now(); }
    legenda = texto;
  }

  function quadro(agora) {
    const dt = Math.min(0.1, (agora - ultimo) / 1000); ultimo = agora;
    // volume suavizado (constante de ~2 s): acompanha o "respirar" do mar, ignora pulsos rápidos
    if (analisador && atual) {
      analisador.getFloatTimeDomainData(dados);
      let s = 0; for (const x of dados) s += x * x;
      nivel += (Math.min(1, Math.sqrt(s / dados.length) * 4) - nivel) * Math.min(1, dt / 2);
    } else nivel += (0 - nivel) * Math.min(1, dt / 2);

    const t = agora / 1000, tocando = !!atual;
    giro += dt * (tocando ? 3 : 1.2) * Math.PI / 180;  // graus por segundo
    const fundo = c.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, W * 0.65);
    fundo.addColorStop(0, `rgb(${58 + nivel * 30},${24 + nivel * 10},${104 + nivel * 30})`);
    fundo.addColorStop(1, "#080418");
    c.fillStyle = fundo; c.fillRect(0, 0, W, H);
    for (const [x, y, b, f] of estrelas) {
      c.globalAlpha = b * (0.55 + 0.45 * Math.sin(t * 0.4 + f)); c.fillStyle = "#fff"; c.fillRect(x, y, 1.6, 1.6);
    }
    const respira = 0.75 + 0.25 * Math.sin(2 * Math.PI * t / 10);
    const brilho = Math.min(1, (tocando ? 0.75 : 0.45) * respira + nivel * 0.5);
    const mistura = anterior ? Math.min(1, (agora - troca) / 2000) : 1;  // troca de símbolo em 2 s
    const desenhar = (nome, alfa) => {
      const img = simbolo(nome), lado = H * 0.95 * (1 + 0.03 * respira);
      c.save(); c.translate(W / 2, H / 2); c.rotate(giro); c.globalAlpha = alfa * brilho;
      c.globalCompositeOperation = "lighter";
      c.drawImage(img, -lado / 2, -lado / 2, lado, lado);
      c.globalAlpha = alfa * brilho * 0.6; c.filter = "blur(10px)";  // halo
      c.drawImage(img, -lado / 2, -lado / 2, lado, lado);
      c.restore();
    };
    if (anterior && mistura < 1) desenhar(anterior, 1 - mistura); else anterior = null;
    desenhar(atualSim, mistura);
    c.globalAlpha = 1; c.fillStyle = OURO; c.textAlign = "center"; c.font = "34px 'Source Sans Pro', sans-serif";
    c.fillText(legenda, W / 2, H - 30);
    c.textAlign = "right"; c.font = "18px 'Source Sans Pro', sans-serif"; c.fillStyle = "#a07a1f";
    c.fillText("feito por Elrofs", W - 20, H - 16);
    requestAnimationFrame(quadro);
  }
  requestAnimationFrame(quadro);

  $("cheia").onclick = () => (document.fullscreenElement ? document.exitFullscreen() : tela.requestFullscreen())
    .catch(() => { $("agora").textContent = "Tela cheia não permitida aqui: use F11 no navegador."; });
  return {faixa};
})();
</script>
"""


def playlist():
    st.subheader("🎶 Playlist")
    lista = st.session_state.playlist
    for i, it in enumerate(lista):
        with st.container(key=f"faixa{i}"):  # classe .st-key-faixaN: mantém o ✕ na mesma linha no celular
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            c1.write(f"{i + 1}. {it['titulo']}")
            if c2.button("✕", key=f"rm{i}", help="Remover"):
                lista.pop(i)
                st.rerun()
    total = sum(it["seg"] for it in lista) // 60
    st.caption(f"Total: {total} min · toca em sequência, sem pausa entre as faixas")
    html = (PLAYER_HTML.replace("__LISTA__", json.dumps(lista))
            .replace("__ACORDES__", json.dumps(ACORDES)).replace("__SINOS__", json.dumps(SINOS))
            .replace("__GRAVACOES__", json.dumps(GRAVACOES)))
    components.html(html, height=490)
    if FFMPEG:
        video_playlist(lista, total)
    if st.button("Limpar playlist"):
        lista.clear()
        st.rerun()


def video_playlist(lista, total_min):
    """Um MP4 com a playlist inteira: cada faixa com seu áudio, legenda e duração."""
    assinatura = json.dumps(lista)  # muda a playlist -> o vídeo antigo deixa de valer
    with st.expander(f"🎬 Criar vídeo da playlist ({total_min} min)"):
        opcoes = list(SIMBOLOS) + ["🔄 Alternar a cada faixa"]
        escolha = st.selectbox("Símbolo", opcoes, key="simbolo_playlist")
        longo = total_min > LIMITE_VIDEO_MIN
        if st.button("Gerar vídeo da playlist", use_container_width=True, disabled=longo):
            nomes = list(SIMBOLOS.values())
            faixas = [(lambda it=it: gerar_wav(it["freqs"], it["seg"], it.get("amb", []), it.get("vol", 1.0)),
                       SIMBOLOS.get(escolha) or nomes[i % len(nomes)],
                       it.get("legenda", it["titulo"].split(" · ")[0]))
                      for i, it in enumerate(lista)]
            with st.spinner(f"Criando o vídeo de {total_min} min... (cerca de 1 min a cada 10 min de playlist)"):
                st.session_state.video_playlist = (gerar_video_faixas(faixas), assinatura)
        if longo:
            st.caption(f"No site, o vídeo da playlist vai até {LIMITE_VIDEO_MIN} min.")
    if st.session_state.get("video_playlist", (None, None))[1] == assinatura:
        mp4 = st.session_state.video_playlist[0]
        st.video(mp4)
        st.download_button("⬇ Baixar vídeo da playlist", mp4, file_name=f"playlist_{total_min}min.mp4",
                           mime="video/mp4", use_container_width=True)
        st.caption(f"{len(mp4) / 1e6:.1f} MB")


if __name__ == "__main__":
    # Autoteste rápido: `python gerador_frequencias.py --test`
    import sys
    if "--test" in sys.argv:
        for fs in ([7.83], [200, 207.83]):
            raw = gerar_wav(fs, 2)
            with wave.open(io.BytesIO(raw)) as wf:
                assert (wf.getnchannels(), wf.getframerate(), wf.getsampwidth(), wf.getnframes()) \
                    == (len(fs), RATE, 2, RATE * 2)
                s = array("h", wf.readframes(wf.getnframes()))
            assert s[0] == 0 and max(s) <= 32767 * 0.8 + 1
        # canais diferentes no binaural: L e R divergem após o fade
        assert s[2 * FADE * 2] != s[2 * FADE * 2 + 1]
        # com ambiente: estéreo, duração exata (passa da emenda do loop de 64 s), sem clipping
        raw = gerar_wav([528], 70, list(AMBIENTES.values()), 0.3)
        with wave.open(io.BytesIO(raw)) as wf:
            assert (wf.getnchannels(), wf.getnframes()) == (2, RATE * 70)
            s = np.frombuffer(wf.readframes(wf.getnframes()), "<i2")
        assert np.abs(s).max() < 32767 and s[:2].tolist() == [0, 0]
        assert raiz_musical(528) == 132 and raiz_musical(4.5) == 144
        if FFMPEG:  # vídeo: duração do áudio, com vídeo e áudio
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(gerar_video(gerar_wav([528], 40), "flor", "528 Hz"))
            info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                                   "-of", "csv=p=0", f.name], capture_output=True, text=True).stdout.split()
            os.remove(f.name)
            assert "video" in info and "audio" in info and abs(float(info[-1]) - 40) < 1, info
            # playlist: faixa mono + faixa binaural com ambiente -> 20 s + 25 s em sequência
            faixas = [(lambda: gerar_wav([528], 20), "flor", "528 Hz"),
                      (lambda: gerar_wav([200, 207.83], 25, ["mar-real"], 0.3), "lotus", "7.83 Hz")]
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(gerar_video_faixas(faixas))
            durs = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=duration",
                                   "-of", "csv=p=0", f.name], capture_output=True, text=True).stdout.split()
            os.remove(f.name)
            assert all(abs(float(d) - 45) < 0.5 for d in durs), durs  # vídeo e áudio com 45 s
        print("ok")
    else:
        main()
