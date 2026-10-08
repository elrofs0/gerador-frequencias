# ✨ Gerador de Frequências

Gere tons puros e batidas binaurais para relaxar, meditar e recomeçar — direto no navegador, em alta definição (16-bit · 44.1 kHz).

- Presets: 2 Hz (delta), 4.5 Hz (theta), 7.83 Hz (Schumann), 10 Hz (alfa), 14 Hz (beta), 40 Hz (gama), 174 Hz, 285 Hz, 528 Hz — ou qualquer frequência personalizada
- Modo binaural para frequências até 40 Hz, incluindo o gama (use fones)
- Modo isocrônico (mesmo alcance): um tom que pulsa na frequência escolhida, funciona também no alto-falante
- Vídeo da playlist mais rápido: o símbolo é desenhado uma vez e cada legenda é somada depois
- Duração de 1 a 30 minutos, player embutido e download em `.wav`
- Playlist: monte uma sequência de frequências e deixe tocando sem parar, com repetição. O player tem faixa anterior/próxima, pausar, volume, lista clicável e tempo, e as faixas se misturam suavemente (crossfade); dá para adicionar e remover faixas sem interromper o som
- Vídeo MP4 com fundo cósmico e geometria sagrada (Flor da Vida, Metatron, Merkabá, Lótus) girando devagar sobre o áudio
- Sons de fundo com a frequência por trás: gravações reais (chuva, mar, pássaros, riacho, fogueira), sons sintéticos (chuva, ondas, vento) e uma melodia ambiente afinada no tom da frequência
- Senoide pura, sem ruído nem salto de fase, gerada com numpy e gravada em blocos de 30 s: pouca memória mesmo em 30 minutos
- Funciona no computador, tablet e celular

## Aviso

Este app é para relaxamento e não substitui tratamento médico: os efeitos atribuídos às frequências não têm comprovação científica. Comece com o volume baixo, principalmente com fones. Quem tem epilepsia ou sensibilidade a sons e luzes deve consultar um médico antes de usar. A visualização não pisca (a luz varia devagar, com suavização de ~2 s).

## Como rodar

```bash
pip install -r requirements.txt
streamlit run gerador_frequencias.py
```

Autoteste do gerador: `python gerador_frequencias.py --test`

## Créditos das gravações

Todas do Wikimedia Commons, recortadas em loops (em `static/` há cada uma em `.wav` e em `.flac`, sem perda e ~45% menor: o navegador baixa o FLAC e cai para o WAV se faltar):

- Fogueira: [Campfire sound ambience.ogg](https://commons.wikimedia.org/wiki/File:Campfire_sound_ambience.ogg), por Glaneur de sons, licença [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) (recortada e convertida em loop mono)

- Chuva: [Rain (1).ogg](https://commons.wikimedia.org/wiki/File:Rain_(1).ogg), por ezwa (domínio público)
- Mar: [Ocean Waves on a Tropical Beach.ogg](https://commons.wikimedia.org/wiki/File:Ocean_Waves_on_a_Tropical_Beach.ogg), por Jarrod Stanley (CC0)
- Pássaros: [Bird call with so-called separated chirps.ogg](https://commons.wikimedia.org/wiki/File:Bird_call_with_so-called_separated_chirps.ogg), por Jidanni (CC0)
- Riacho: [433589 jackthemurray stream-river-water-up-close.wav](https://commons.wikimedia.org/wiki/File:433589_jackthemurray_stream-river-water-up-close.wav), por jackthemurray (CC0)

---

✦ feito por Elrofs
