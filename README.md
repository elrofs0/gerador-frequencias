# ✨ Gerador de Frequências

Gere tons puros e batidas binaurais para relaxar, meditar e recomeçar — direto no navegador, em alta definição (16-bit · 44.1 kHz).

- Presets: 4.5 Hz, 7.83 Hz (Schumann), 10 Hz, 174 Hz, 285 Hz, 528 Hz — ou qualquer frequência personalizada
- Modo binaural para frequências abaixo de 40 Hz (use fones)
- Duração de 1 a 30 minutos, player embutido e download em `.wav`
- Playlist: monte uma sequência de frequências e deixe tocando sem parar, com repetição
- Senoide gerada só com a biblioteca padrão do Python (`wave`, `struct`, `math`), sem ruído
- Funciona no computador, tablet e celular

## Como rodar

```bash
pip install -r requirements.txt
streamlit run gerador_frequencias.py
```

Autoteste do gerador: `python gerador_frequencias.py --test`

---

✦ feito por Elrofs
