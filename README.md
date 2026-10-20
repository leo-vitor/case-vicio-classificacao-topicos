# Case — Classificação de tópicos (duas fases)

Repositório único para as duas fases do case. A **Fase 1** está congelada na tag
[`v1-fase1`](https://github.com/leo-vitor/case-vicio-classificacao-topicos/releases/tag/v1-fase1);
a **Fase 2** vive em [`fase2/`](fase2/) e é autocontida (não importa nada de `fase1/`).

| Fase | O que é | Onde | Entrega |
|---|---|---|---|
| **1** | Classificação assistida com LLM verificador (359 questões) | [`fase1/`](fase1/) | `fase1/publicacao.csv`, `fase1/previsao.txt`, [relatório](fase1/report/relatorio.pdf) |
| **2** | Classificação seletiva **sem LLM** (659 questões) | [`fase2/`](fase2/) | em construção — ver [`fase2/README.md`](fase2/README.md) |

## A evolução entre as fases

A Fase 2 nasce de uma leitura crítica da Fase 1. O que mudou:

1. **Sem LLM na decisão.** A Fase 2 recupera candidatos e decide por regra + modelo
   supervisionado pequeno. LLM só entraria offline (limpeza, embeddings), versionado.
2. **Só rótulos de especialista.** A Fase 1 usou rótulos assistidos por IA para estimar
   qualidade; a Fase 2 usa exclusivamente as 100 marcações humanas, para não medir
   "concordância com IA".
3. **Teto estatístico explícito.** Com 100 rótulos, o limite inferior de Wilson de 95%
   exige ~73 acertos em 73 publicadas. Publicar pouco e com evidência, não publicar 62%.
4. **Validação agrupada.** Folds repetidos, estratificados, com near-duplicatas no mesmo
   fold, e limiar escolhido **fora da dobra**. Sem isso a precisão reportada é otimista.

As decisões estão registradas em [`docs/decisoes.md`](docs/decisoes.md).

## Estrutura

```
├── README.md            este arquivo (mapa das duas fases)
├── docs/decisoes.md     decisões metodológicas e por quê
├── fase1/               ENTREGA CONGELADA (tag v1-fase1)
│   ├── src/             pipeline com LLM verificador
│   ├── data/            dicionário curado (anexos não versionados)
│   ├── outputs/         artefatos e avaliação
│   ├── report/          relatório final (PDF/LaTeX)
│   ├── publicacao.csv   359 questões
│   └── previsao.txt     precisão 0,86 [0,74–0,94]
└── fase2/               CASE NOVO (sem LLM)
    ├── src/             recuperação + protocolo + baseline
    ├── data/            anexos do case (não versionados)
    ├── artefatos/       saídas geradas (não versionadas)
    └── docs/            resultados por etapa
```

## Como rodar

### Fase 1 (histórico, congela a entrega)

```bash
cd fase1
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
cp ../fase1/.env.example .env      # backend do juiz (Gemini/OpenAI/Ollama)
.venv/bin/python -m src.clean
.venv/bin/python -m src.candidates
.venv/bin/python -m src.judge
.venv/bin/python -m src.decide
```

Os anexos (`data/questoes.jsonl`, `data/temas.csv`) não são versionados.

### Fase 2 (atual, sem LLM)

```bash
cd fase2
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
# coloque os anexos em fase2/data/
.venv/bin/python -m src.clean
.venv/bin/python -m src.baseline
```

Detalhes em [`fase2/README.md`](fase2/README.md).

## Números da Fase 2 (Etapa 1, baseline lexical)

- Melhor recuperador: TF-IDF de caracteres — recall hierárquico 0,91 no top-10.
- Precisão 95% só aparece em ~10% de cobertura; a cobertura teórica máxima é ~84%.
- Nenhuma configuração lexical passa no critério Wilson ≥ 0,95 fora da dobra.

Ou seja: o baseline justifica as próximas etapas (reranker + regra do pai + `fora`
conservador). Resultado completo em [`fase2/docs/etapa1_baseline.md`](fase2/docs/etapa1_baseline.md).
