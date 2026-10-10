"""Gerador de Frequências Terapêuticas e Tons Puros — rode com: streamlit run gerador_frequencias.py"""
import io
import json
import os
import wave
from array import array

import numpy as np  # já vem com o Streamlit
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
    "2 Hz — Delta: sono profundo, descanso": 2.0,
    "4.5 Hz — Theta profundo: meditação, introspecção": 4.5,
    "7.83 Hz — Ressonância Schumann: aterramento, calma": 7.83,
    "10 Hz — Alpha: relaxamento alerta, foco leve": 10.0,
    "14 Hz — Beta: foco, atenção": 14.0,
    "40 Hz — Gama: concentração, memória": 40.0,
    "174 Hz — Solfeggio: alívio de tensão, segurança": 174.0,
    "285 Hz — Solfeggio: restauração, bem-estar": 285.0,
    "528 Hz — Solfeggio: harmonia, 'frequência do amor'": 528.0,
    "852 Hz — Solfeggio: intuição, 'Chama Violeta'": 852.0,
    "963 Hz — Solfeggio: conexão, unidade": 963.0,
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


@st.cache_resource  # o array é só lido: cache_data copiaria ~20 MB a cada chamada
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


BLOCO = RATE * 30  # o WAV é gerado e gravado em blocos de 30 s: o pico de memória fica perto do tamanho do arquivo


def tom(freqs: list[float], idx: np.ndarray, total: int, pulso: float | None = None) -> np.ndarray:
    """Os quadros `idx` do tom: float64, uma coluna por canal, pico 1, com fade nas pontas.
    A fase sai direto do índice da amostra (float64 sobra em precisão), então não há emenda
    entre blocos nem salto de fase, mesmo em frequências como 7.83 Hz."""
    x = np.sin(np.outer(idx, 2 * np.pi * np.asarray(freqs, np.float64) / RATE))
    if pulso:  # isocrônico: a portadora liga e desliga suavemente `pulso` vezes por segundo (0..1)
        x = x * (0.5 * (1 + np.sin(2 * np.pi * pulso * idx / RATE)))[:, None]
    return x * np.minimum(1, np.minimum(idx, total - 1 - idx) / FADE)[:, None]


def gerar_wav(freqs: list[float], segundos: int, ambientes=(), vol_freq=1.0, pulso: float | None = None) -> bytes:
    """Uma frequência por canal: [f] = mono, [esq, dir] = estéreo (binaural).
    `pulso` (Hz) liga o modo isocrônico (um tom só, pulsando). Com `ambientes`, mistura as camadas por cima e a frequência fica ao fundo (`vol_freq`).
    Gera e grava em blocos de BLOCO quadros: o pico de memória é pouco mais que o próprio WAV."""
    total, ch = RATE * segundos, len(freqs)
    if ambientes:
        sinteticos = [a for a in ambientes if a not in GRAVACOES]
        camadas = [ambiente(sinteticos, raiz_musical(freqs[0]))] if sinteticos else []
        camadas += [gravacao(a) for a in ambientes if a in GRAVACOES]
        escala = 1 / max(1.0, 0.8 * vol_freq + 0.8)  # pico máximo possível da soma
        rampa = 3 * RATE  # fade de 3 s no ambiente

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2 if ambientes else ch)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        for i0 in range(0, total, BLOCO):
            idx = np.arange(i0, min(total, i0 + BLOCO))
            x = tom(freqs, idx, total, pulso)
            if ambientes:
                amb = np.tanh(sum(c[idx % len(c)] for c in camadas))  # cada loop no seu tamanho; tanh = limitador suave
                g = np.minimum(1, np.minimum(idx, total - idx) / rampa)[:, None]
                mix = (x * (AMP / 32767) * vol_freq + 0.8 * amb * g) * escala
                quadros = np.rint(mix * 32767)
            else:
                quadros = np.rint(AMP * x)
            wf.writeframes(quadros.astype("<i2").tobytes())  # "<i2": WAV é little-endian em qualquer máquina
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
        chama_violeta()
    with st.container(border=True):
        controles()
    with st.container(border=True):  # sempre visível: o player também toca "Meu vídeo" sem playlist
        playlist()
    st.caption("⚠ Este app é para relaxamento e não substitui tratamento médico: os efeitos atribuídos às "
               "frequências não têm comprovação científica. Comece com o volume baixo, principalmente "
               "com fones. Quem tem epilepsia ou sensibilidade a sons e luzes deve consultar um médico antes de usar.")
    st.caption("Senoide pura · 16-bit · 44.1 kHz · Som de fogueira: “Campfire sound ambience”, "
               "Glaneur de sons, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), via Wikimedia Commons")


def chama_violeta():
    """Atalho de um clique: frequência baixinha + melodia, em repetição, com chamas violetas."""
    st.markdown("**💜 Chama Violeta · Saint Germain**")
    st.caption("Frequência suave ao fundo com melodia ambiente, tocando sem parar, "
               "e chamas violetas na visualização. Ideal para deixar tocando no notebook.")
    for col, f in zip(st.columns(2), (852, 963)):
        if col.button(f"💜 {f} Hz", key=f"violeta{f}", use_container_width=True):
            st.session_state.setdefault("playlist", []).append({
                "titulo": f"💜 Chama Violeta · {f} Hz + melodia ambiente · 30 min", "freqs": [f],
                "seg": 30 * 60, "amb": ["melodia"], "vol": 0.3, "raiz": raiz_musical(f), "pulso": None,
                "legenda": f"{f} Hz · Chama Violeta", "tema": "violeta"})
            st.toast("Adicionado à playlist. Aperte ▶ no player lá embaixo.", icon="💜")


def controles():
    opcoes = list(PRESETS) + ["Personalizada"]
    # começa no theta (4.5 Hz), como antes de entrarem os presets de delta, beta e gama
    preset = st.selectbox("Escolha uma frequência", opcoes, index=next(i for i, k in enumerate(opcoes) if k.startswith("4.5 Hz")))
    if preset == "Personalizada":
        freq = st.number_input("Frequência (Hz)", min_value=0.1, max_value=22000.0,
                               value=432.0, step=0.01, format="%.2f")
    else:
        freq = PRESETS[preset]

    minutos = st.slider("Duração (minutos)", 1, 30, 10)

    # Binaural e isocrônico só fazem sentido para frequências baixas (até 40 Hz, o gama); acima disso, tom puro.
    # Binaural é o padrão: tons de 20–40 Hz também são fracos nos alto-falantes e rendem mais como batida.
    modo = "Tom puro"
    if freq <= 40:
        modo = st.radio("Modo", ["Binaural", "Isocrônico", "Tom puro"], horizontal=True,
                        help="Binaural: um tom diferente em cada ouvido (use fones). "
                             "Isocrônico: um tom que pulsa, funciona também no alto-falante.")
    binaural, isocronico = modo == "Binaural", modo == "Isocrônico"
    pulso = None
    if binaural or isocronico:
        portadora = st.number_input("Portadora (Hz)", min_value=20.0, max_value=1000.0,
                                    value=200.0, step=1.0, format="%.2f")
    if binaural:
        freqs = [portadora, portadora + freq]
        st.caption(f"Esquerdo {portadora:g} Hz · Direito {portadora + freq:g} Hz → "
                   f"o cérebro percebe uma batida de {freq:g} Hz. Comece com o volume baixo.")
        nome = f"binaural_{freq:g}Hz_portadora{portadora:g}_{minutos}min.wav"
    elif isocronico:
        freqs, pulso = [portadora], freq
        st.caption(f"Tom de {portadora:g} Hz que pulsa {freq:g} vezes por segundo. "
                   "Não precisa de fones. Comece com o volume baixo.")
        nome = f"isocronico_{freq:g}Hz_portadora{portadora:g}_{minutos}min.wav"
    else:
        freqs = [freq]
        nome = f"tom_{freq:g}Hz_{minutos}min.wav"
        if freq < 20:
            st.info("Abaixo de 20 Hz o tom puro é praticamente inaudível. Use o modo binaural ou isocrônico.")

    escolhidos = st.multiselect("Sons de fundo (opcional)", list(AMBIENTES),
                                placeholder="Chuva, ondas, vento, melodia...")
    ambientes = [AMBIENTES[a] for a in escolhidos]
    vol_freq = 1.0
    if ambientes:
        vol_freq = st.slider("Volume da frequência", 5, 100, 30, format="%d%%") / 100
        st.caption("A frequência fica ao fundo; a melodia é afinada no mesmo tom dela.")
        nome = nome.replace(".wav", "_" + "-".join(ambientes) + ".wav")

    sufixo = " · binaural" if binaural else " · isocrônico" if isocronico else ""
    col1, col2 = st.columns(2)
    longo = minutos > LIMITE_MIN
    if col1.button("Gerar áudio", type="primary", use_container_width=True, disabled=longo):
        with st.spinner(f"Gerando {minutos} min..."):
            legenda = f"{freq:g} Hz" + sufixo
            st.session_state.audio = (gerar_wav(freqs, minutos * 60, ambientes, vol_freq, pulso), nome, legenda)
            st.session_state.pop("video", None)
    if col2.button("＋ Adicionar à playlist", use_container_width=True):
        titulo = (f"{freq:g} Hz binaural (portadora {freqs[0]:g} Hz)" if binaural
                  else f"{freq:g} Hz isocrônico (portadora {freqs[0]:g} Hz)" if isocronico
                  else f"{freq:g} Hz") + "".join(f" + {a}" for a in escolhidos) + f" · {minutos} min"
        st.session_state.setdefault("playlist", []).append(
            {"titulo": titulo, "freqs": freqs, "seg": minutos * 60, "amb": ambientes,
             "vol": vol_freq, "raiz": raiz_musical(freqs[0]), "pulso": pulso,
             "legenda": f"{freq:g} Hz" + sufixo})
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
# Vive em player/index.html, como componente do Streamlit: a lista chega por mensagem e, com
# `key` fixa, adicionar/remover faixas não recarrega o player, então o som não é interrompido.
# A troca de faixa é agendada no relógio de áudio (onended), então continua tocando
# mesmo com a aba em segundo plano.
PLAYER = components.declare_component(
    "player_playlist", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "player"))


def playlist():
    st.subheader("🎶 Playlist")
    lista = st.session_state.setdefault("playlist", [])
    if not lista:
        st.caption("Adicione frequências acima, ou toque um vídeo do seu computador em "
                   "repetição com 📼 Meu vídeo.")
    for i, it in enumerate(lista):
        with st.container(key=f"faixa{i}"):  # classe .st-key-faixaN: mantém o ✕ na mesma linha no celular
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            c1.write(f"{i + 1}. {it['titulo']}")
            if c2.button("✕", key=f"rm{i}", help="Remover"):
                lista.pop(i)
                st.rerun()
    total = sum(it["seg"] for it in lista) // 60
    if lista:
        st.caption(f"Total: {total} min · toca em sequência, sem pausa entre as faixas")
    PLAYER(lista=lista, acordes=ACORDES, sinos=SINOS, gravacoes=GRAVACOES, key="player_playlist")
    if not lista:
        return
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
            faixas = [(lambda it=it: gerar_wav(it["freqs"], it["seg"], it.get("amb", []), it.get("vol", 1.0), it.get("pulso")),
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
        # emenda entre blocos: ao cruzar BLOCO (e depois 2×BLOCO) a senoide segue exata, sem salto de fase
        raw = gerar_wav([7.83], 70)
        with wave.open(io.BytesIO(raw)) as wf:
            s = np.frombuffer(wf.readframes(wf.getnframes()), "<i2").astype(int)
        for corte in (BLOCO, 2 * BLOCO):
            i = np.arange(corte - 50, corte + 50)
            assert np.abs(s[i] - np.rint(AMP * np.sin(2 * np.pi * 7.83 * i / RATE))).max() <= 1
        # isocrônico: mono, a envoltória pulsa na frequência pedida (4 Hz -> 4 ciclos por segundo)
        raw = gerar_wav([200], 3, pulso=4)
        with wave.open(io.BytesIO(raw)) as wf:
            assert wf.getnchannels() == 1
            s = np.frombuffer(wf.readframes(wf.getnframes()), "<i2").astype(float)
        env = np.abs(s).reshape(-1, RATE // 100).max(axis=1)  # envoltória em janelas de 10 ms
        env = env[FADE // (RATE // 100) + 5:-(FADE // (RATE // 100) + 5)]
        assert env.max() > 0.9 * AMP and env.min() < 0.1 * AMP
        picos = ((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > 0.8 * AMP)).sum()
        assert 10 <= picos <= 13, picos  # ~2,8 s de envoltória x 4 Hz
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
