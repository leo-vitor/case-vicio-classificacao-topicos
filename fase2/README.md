# Fase 2 — Classificação de tópicos (659 questões, decisão sem LLM)

Pipeline que gera o `publicacao.csv` para as 659 questões do case novo **sem chamar
nenhum modelo de linguagem** — recuperação de candidatos + decisão seletiva, tudo
offline e determinístico.

## O problema, em números

| Item | Valor |
|---|---|
| Questões | 659 (359 antigas + 300 novas) |
| Temas publicáveis | 371 (109 nível 1, 262 nível 2) |
| Rótulos de especialista | 100 (`data/folha_verdade.csv`), todas Q0001–Q0359 |
| Saída | `publicar` / `revisar` / `fora` + tema sugerido + confiança |
| Meta | precisão ≥ 95% nas publicadas, maximizando cobertura |
| Avaliação | apenas as 559 fora da folha-verdade |

**Regra de acerto (LEIA-ME):** publicar no tema central, num extra, ou num **pai** ou
**filho** direto de um deles conta como certo. Irmão (outro subtema do mesmo tema)
conta como erro.

## Por que recuperação e não um classificador de 371 classes

São 61 temas centrais distintos em 100 exemplos, e 42 deles com **1 único** exemplo.
Não há dados para um classificador plano nem para um transformer. O desenho é:

```
questão → limpeza → recuperação de candidatos → features → reranker
        → score calibrado → regra seletiva → publicar / revisar / fora
```

## Estado atual

- [x] **Etapa 0 — protocolo** (`src/protocolo.py`): régua de acerto, folds repetidos
      estratificados com near-duplicatas agrupadas, Wilson, limiar escolhido **fora da dobra**.
- [x] **Etapa 1 — baseline lexical** (`src/baseline.py`): TF-IDF palavra/char, BM25, RRF.
      Resultado em [`docs/etapa1_baseline.md`](docs/etapa1_baseline.md).
- [x] **Etapa 2 — embeddings densos locais**: **descartados**. `multilingual-e5-large`
      com temas enriquecidos: 0,53–0,68 sozinho e 0,72–0,75 em fusão, contra 0,74 do
      `rrf_all`; melhor fusão +1 questão, IC pareado cruza zero. Detalhes em
      [`docs/experimento_embeddings_v2.md`](docs/experimento_embeddings_v2.md).
- [x] **Etapa 3 — reranker de candidatos**: **descartado**. Empata ou perde da regra v0.
- [x] **Etapa 4 — decisão seletiva** (`src/decisao.py`): regra do pai + consenso entre
      recuperadores + confiança. Publica 115/659.
- [x] **Etapa 5 — entrega**: `publicacao.csv` e `previsao.txt` (precisão 0,76 [0,53–0,90]
      na leitura aninhada; 0,91 [0,76–0,99] é o teto in-sample; cobertura 0,17 nas 559;
      0,20 na folha).
- [x] **Auditoria da camada de decisão** (`src/conformal.py`, `src/auditoria.py`): controle
      de risco conformal, precisão certificável (95% é impossível com 100 rótulos),
      conjuntos conformais + ancestral comum, protocolo aninhado **sem vazamento**,
      comparação com regras manuais e manifesto de proveniência.
      Resultado em [`docs/auditoria.md`](docs/auditoria.md).
- [ ] **Enriquecimento jurídico da taxonomia** (próximo passo): descrições
      discriminativas geradas **offline**, versionadas, sem ver as questões.
      Briefing de hand-off em [`docs/briefing_enriquecimento.md`](docs/briefing_enriquecimento.md).

Resumo da entrega, resultados e limites: [`docs/entrega.md`](docs/entrega.md).

## Como rodar

Os anexos do case devem estar em `data/` (`questoes.jsonl`, `temas.csv`,
`folha_verdade.csv`, `entrega_modelo.csv`). Eles não são versionados, igual à Fase 1.

```bash
cd fase2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

./scripts/regenerar.sh   # pipeline completo: publicacao.csv + previsao.txt + artefatos
```

O script roda `clean → baseline → confianca → decisao → conformal → auditoria → previsao`
(e, no fim, `diagnostico` e `regra_final`) e para no primeiro erro. Leva ~60 s em um núcleo,
sem rede e sem LLM na decisão. Para um módulo isolado: `.venv/bin/python -m src.<modulo>`.
O relatório compila com `pdflatex` em `report/`.

Saídas em `artefatos/` (reconstruíveis, por isso fora do git):

| Arquivo | O que é |
|---|---|
| `questoes_limpas.csv` | 659 questões com texto limpo |
| `recuperacao.csv` | recall@k exato/hierárquico por recuperador |
| `curva_precisao_cobertura.csv` | curva completa (recuperador × sinal × limiar) |
| `ponto_operacao_oof.csv` | precisão/cobertura com limiar escolhido fora da dobra |
| `diagnostico_gold.json` | composição da folha-verdade |

## Estrutura

```
fase2/
├── data/            anexos do case (não versionados) + dicionário jurídico curado
├── src/
│   ├── config.py        caminhos, semente, parâmetros
│   ├── clean.py         HTML → texto
│   ├── temas.py         árvore + régua de acerto (pai/filho; irmão não conta)
│   ├── dicionario.py    expansão de consulta (offline, curado à mão)
│   ├── recuperacao.py   TF-IDF palavra/char, BM25, RRF
│   ├── protocolo.py     folds, Wilson, curva, limiar out-of-fold, Beta-Binomial
│   ├── baseline.py      Etapa 1 (A0/A1)
│   ├── confianca.py     confiança no nível da questão + regra do pai
│   ├── decisao.py       regra seletiva → publicacao.csv
│   ├── previsao.py      previsao.txt
│   ├── artefato.py      base compartilhada (folds, p_oof, features)
│   ├── conformal.py     CRC, precisão certificável, conjuntos + ancestral comum
│   └── auditoria.py     aninhado corrigido, regras × logística, manifesto
├── artefatos/       saídas geradas (não versionadas)
└── docs/            resultados e decisões
```

## Origem do código

`clean.py`, `temas.py`, `dicionario.py`, `recuperacao.py` foram adaptados de
`fase1/src/`. A Fase 2 é autocontida: não importa nada de `fase1/` e roda sozinha.
As mudanças estão documentadas no topo de cada arquivo.
