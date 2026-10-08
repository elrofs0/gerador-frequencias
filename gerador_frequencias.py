"""Gerador de Frequências Terapêuticas e Tons Puros — rode com: streamlit run gerador_frequencias.py"""
import io
import math
import struct
import wave
from array import array
from fractions import Fraction

import streamlit as st

RATE = 44100
AMP = 0.8 * 32767  # headroom de ~2 dB, evita clipping
FADE = int(RATE * 0.05)  # 50 ms de fade in/out para não estalar

PRESETS = {
    "4.5 Hz — Theta profundo: meditação, introspecção": 4.5,
    "7.83 Hz — Ressonância Schumann: aterramento, calma": 7.83,
    "10 Hz — Alpha: relaxamento alerta, foco leve": 10.0,
    "174 Hz — Solfeggio: alívio de tensão, segurança": 174.0,
    "285 Hz — Solfeggio: restauração, bem-estar": 285.0,
    "528 Hz — Solfeggio: harmonia, 'frequência do amor'": 528.0,
}


def gerar_wav(freqs: list[float], segundos: int) -> bytes:
    """Uma frequência por canal: [f] = mono, [esq, dir] = estéreo (binaural)."""
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

    if struct.pack("=h", 1) != struct.pack("<h", 1):  # WAV é little-endian
        amostras.byteswap()

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(ch)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(amostras.tobytes())
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
    st.caption("Senoide pura · 16-bit · 44.1 kHz · gerado no seu computador, nada é enviado")


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

    if st.button("Gerar áudio", type="primary", use_container_width=True):
        with st.spinner(f"Gerando {minutos} min..."):
            st.session_state.audio = (gerar_wav(freqs, minutos * 60), nome)

    if "audio" in st.session_state:
        dados, nome = st.session_state.audio
        st.audio(dados, format="audio/wav")
        st.download_button("⬇ Baixar " + nome, dados, file_name=nome,
                           mime="audio/wav", use_container_width=True)
        st.caption(f"{len(dados) / 1e6:.1f} MB")


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
        print("ok")
    else:
        main()
