# Case — Classificação de tópicos (duas fases)

Repositório único para as duas fases do case. A **Fase 1** está congelada na tag
[`v1-fase1`](https://github.com/leo-vitor/case-vicio-classificacao-topicos/releases/tag/v1-fase1);
a **Fase 2** está em [`fase2/`](fase2/), é autocontida (não importa nada de `fase1/`) e a
versão final está na tag
[`v5-entrega-final`](https://github.com/leo-vitor/case-vicio-classificacao-topicos/releases/tag/v5-entrega-final).

| Fase | O que é | Onde | Entrega |
|---|---|---|---|
| **1** | Classificação assistida com LLM verificador (359 questões) | [`fase1/`](fase1/) | `fase1/publicacao.csv`, `fase1/previsao.txt`, [relatório](fase1/report/relatorio.pdf) |
| **2** | Classificação seletiva **sem LLM na decisão** (659 questões) | [`fase2/`](fase2/) | `fase2/publicacao.csv`, `fase2/previsao.txt`, [relatório](fase2/report/relatorio.pdf), [entrega](fase2/docs/entrega.md) + [auditoria](fase2/docs/auditoria.md) |

## A evolução entre as fases

A Fase 2 nasce de uma leitura crítica da Fase 1. O que mudou:

1. **Sem LLM na decisão.** A Fase 2 recupera candidatos e decide por regra + modelo
   supervisionado pequeno. O LLM entra uma única vez, offline, para enriquecer a descrição
   dos temas; o artefato é versionado e a decisão não chama modelo.
2. **Só rótulos de especialista.** A Fase 1 usou rótulos assistidos por IA para estimar
   qualidade; a Fase 2 usa exclusivamente as 100 marcações humanas, para não medir
   "concordância com IA".
3. **Teto estatístico explícito.** Com 100 rótulos, a regra de zero erros exige umas 60
   publicadas sem erro para garantir 95%; com 20, só 86%. Publicar pouco e com evidência,
   não publicar 62%.
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
└── fase2/               CASE NOVO (sem LLM na decisão)
    ├── src/             recuperação + protocolo + decisão + auditoria
    ├── data/            anexos do case (não versionados)
    ├── artefatos/       saídas geradas (não versionadas)
    ├── report/          relatório final (PDF/LaTeX)
    ├── scripts/         regeneração do pipeline
    ├── publicacao.csv   659 questões (115 publicar / 544 revisar)
    ├── previsao.txt     precisão 0,76 [0,53–0,90], cobertura 0,17
    └── docs/            entrega, baseline e auditoria
```

## Como rodar

### Fase 1 (histórico, congela a entrega)

```bash
cd fase1
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
cp .env.example .env               # backend do juiz (Gemini/OpenAI/Ollama)
.venv/bin/python -m src.clean
.venv/bin/python -m src.candidates
.venv/bin/python -m src.judge
.venv/bin/python -m src.decide
```

Os anexos (`data/questoes.jsonl`, `data/temas.csv`) não são versionados.

### Fase 2 (entrega final, sem LLM na decisão)

```bash
cd fase2
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
# coloque os anexos do case em fase2/data/
./scripts/regenerar.sh
```

O script roda o pipeline completo (`clean → baseline → confiança → decisão → conformal →
auditoria → previsão`) e refaz `publicacao.csv` e `previsao.txt` em cerca de um minuto.
Para rodar um módulo isolado: `.venv/bin/python -m src.<modulo>`.

Detalhes em [`fase2/README.md`](fase2/README.md).

## Números da Fase 2

| Item | Valor |
|---|---|
| Decisões nas 659 | 115 `publicar` / 544 `revisar` / 0 `fora` |
| Cobertura nas 559 fora da folha | 0,17 (94/559 — antigas 0,15, novas 0,18) |
| Precisão prevista | 0,76 [0,53–0,90] (aninhada corrigida; teto in-sample 0,95 [0,76–0,99]) |
| Regra | consenso ≥ 0,75 **e** confiança ≥ 0,895946 (logística de 13 features) |
| Precisão in-sample nos 100 | 19/20 = 0,95 (leitura literal da régua; estrita 0,50) |
| Precisão aninhada, sem vazamento | 13/17 = 0,765 |
| O que 100 rótulos **certificam** | ~80% de precisão (a 20% de erro); 95% e 90% não são certificáveis. |

Três achados que valem mais que o número final: a régua do case é o que sustenta a meta
(na leitura estrita a precisão cai para 0,50); a validação aninhada anterior tinha
vazamento (33 → 17 publicações ao corrigir); e não existe limiar que prove 95% com 100
rótulos. Detalhes em [`fase2/docs/auditoria.md`](fase2/docs/auditoria.md).
