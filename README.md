# ✨ Gerador de Frequências

Gere tons puros e batidas binaurais para relaxar, meditar e recomeçar — direto no navegador, em alta definição (16-bit · 44.1 kHz).

- Presets: 4.5 Hz, 7.83 Hz (Schumann), 10 Hz, 174 Hz, 285 Hz, 528 Hz — ou qualquer frequência personalizada
- Modo binaural para frequências abaixo de 40 Hz (use fones)
- Duração de 1 a 30 minutos, player embutido e download em `.wav`
- Playlist: monte uma sequência de frequências e deixe tocando sem parar, com repetição
- Sons de fundo com a frequência por trás: gravações reais (chuva, mar, pássaros, riacho), sons sintéticos (chuva, ondas, vento) e uma melodia ambiente afinada no tom da frequência
- Senoide gerada só com a biblioteca padrão do Python (`wave`, `struct`, `math`), sem ruído
- Funciona no computador, tablet e celular

## Como rodar

```bash
pip install -r requirements.txt
streamlit run gerador_frequencias.py
```

Autoteste do gerador: `python gerador_frequencias.py --test`

## Créditos das gravações

Todas do Wikimedia Commons, em domínio público ou CC0, recortadas em loops:

- Chuva: [Rain (1).ogg](https://commons.wikimedia.org/wiki/File:Rain_(1).ogg), por ezwa (domínio público)
- Mar: [Ocean Waves on a Tropical Beach.ogg](https://commons.wikimedia.org/wiki/File:Ocean_Waves_on_a_Tropical_Beach.ogg), por Jarrod Stanley (CC0)
- Pássaros: [Bird call with so-called separated chirps.ogg](https://commons.wikimedia.org/wiki/File:Bird_call_with_so-called_separated_chirps.ogg), por Jidanni (CC0)
- Riacho: [433589 jackthemurray stream-river-water-up-close.wav](https://commons.wikimedia.org/wiki/File:433589_jackthemurray_stream-river-water-up-close.wav), por jackthemurray (CC0)

---

✦ feito por Elrofs
