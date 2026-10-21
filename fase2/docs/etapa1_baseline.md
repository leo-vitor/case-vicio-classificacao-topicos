# Etapa 1 — Baseline lexical e protocolo honesto

Rodado em 2026-10-20 com `python -m src.baseline` (offline, sem LLM).
Fonte: `artefatos/recuperacao.csv`, `artefatos/curva_precisao_cobertura.csv`,
`artefatos/ponto_operacao_oof.csv`.

## Composição da folha-verdade (única base rotulada)

| Item | Valor |
|---|---|
| Questões | 100 (todas Q0001–Q0359) |
| `fora_da_taxonomia` | 8 |
| Com `extras_ids` | 39 |
| Temas centrais distintos | 61 |
| Near-duplicatas internas | 0 |

Estratos: Penal 40 · Processo Penal 30 · Legislação Especial 12 · Criminologia 10 · fora 8.

Como só 100 questões são rotuladas e **as 300 novas não têm rótulo**, tudo abaixo vale
para as antigas. A previsão para as 559 terá de ser estratificada e conservadora.

## recall@k (exato / hierárquico), n = 92 com tema

| Recuperador | k=1 | k=3 | k=5 | k=10 | k=20 |
|---|---|---|---|---|---|
| tfidf | 0,40 / 0,61 | 0,57 / 0,70 | 0,64 / 0,72 | 0,76 / 0,83 | 0,80 / 0,88 |
| **tfidf_char** | 0,33 / 0,51 | 0,64 / 0,78 | 0,75 / 0,87 | **0,85 / 0,91** | **0,89 / 0,95** |
| bm25 | 0,28 / 0,46 | 0,46 / 0,61 | 0,50 / 0,66 | 0,55 / 0,71 | 0,70 / 0,79 |
| rrf_tfidf_bm25 | 0,38 / 0,53 | 0,53 / 0,70 | 0,66 / 0,76 | 0,72 / 0,79 | 0,75 / 0,83 |
| rrf_all | 0,40 / 0,59 | 0,61 / 0,73 | 0,68 / 0,79 | 0,75 / 0,85 | 0,87 / 0,92 |

Leituras:

1. **TF-IDF de caracteres é o melhor recuperador** (hier@10 = 0,91; hier@20 = 0,95).
   Faz sentido: os títulos da árvore são curtos e o vocab do domínio é morfológico
   ("hediondo", "hediondos", "hediondez").
2. **BM25 sozinho é o pior** e o RRF só serve para *recuperar* o que o tfidf perde —
   não supera o char. Se o char continuar vencendo nas próximas etapas, BM25 e RRF
   não entram na entrega (regra de parada: sem ganho, sem complexidade).
3. O teto do juiz sobre o top-10 é **0,91** (84/92). Ou seja, mesmo um reranker
   perfeito no top-10 não passa de ~84% de cobertura, e ainda precisaria acertar
   precisão de 95% nesse subconjunto.

## Fronteira precisão × cobertura (melhor precisão com cobertura ≥ x)

| Recuperador | cob≥0,1 | ≥0,2 | ≥0,3 | ≥0,4 | ≥0,5 | ≥0,6 | ≥0,7 | ≥0,8 |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0,81 | 0,80 | 0,71 | 0,66 | 0,66 | 0,66 | 0,64 | 0,63 |
| **tfidf_char** | **1,00** | **0,82** | 0,76 | 0,73 | 0,65 | 0,63 | 0,59 | 0,57 |
| bm25 | 0,82 | 0,61 | 0,61 | 0,58 | 0,56 | 0,50 | 0,49 | 0,46 |
| rrf_tfidf_bm25 | 0,76 | 0,76 | 0,76 | 0,76 | 0,67 | 0,67 | 0,62 | 0,56 |
| rrf_all | 0,79 | 0,79 | 0,79 | **0,76** | 0,72 | 0,70 | 0,64 | 0,60 |

`rrf_all` tem a fronteira mais plana (0,79 até cobertura 0,3 e 0,76 em 0,4), o que sugere que a
fusão ajuda a **estabilizar** a decisão, mesmo sem melhorar o recall. Fica como
candidato; decide-se pelo ponto de operação, não pelo recall.

## Ponto de operação com limiar escolhido fora da dobra

Folds: 5 × 5 repetidos, estratificados por disciplina, near-duplicatas agrupadas.
O limiar é escolhido no treino de cada fold (precisão ≥ 0,95) e medido no teste.

| Recuperador | Sinal | Publicados | Acertos | Precisão | IC 95% (Wilson) | Cobertura |
|---|---|---|---|---|---|---|
| rrf_all | rel | 1 | 1 | 1,00 | 0,21–1,00 | 0,01 |
| tfidf_char | abs | 11 | 10 | 0,91 | 0,62–0,98 | 0,11 |
| tfidf | abs | 3 | 2 | 0,67 | 0,21–0,94 | 0,03 |

Critério "limite inferior de Wilson ≥ 0,95": **nenhuma** configuração lexical passa.
Não é surpresa: para o limite inferior bater 95% são precisos cerca de **73 acertos
em 73 publicadas**. Com 100 rótulos, a estratégia é publicar pouco e muito bem — não
manter a cobertura de 62% da Fase 1.

## Conclusão da Etapa 1

O baseline lexical **não** atinge 95% com cobertura útil:

- 95% de precisão só aparece em torno de 10% de cobertura;
- a cobertura máxima teórica (recall hierárquico no top-10) é ~84%.

Portanto as próximas etapas são o que decide o case:

1. **Reranker sobre features de candidato** (Etapa 3) — usa os sinais que o top-1
   sozinho ignora: margem, entropia, relação pai/filho, gêmeo, disciplina, lei citada.
2. **Regra do pai** (Etapa 4) — quando a incerteza é entre irmãos do mesmo ramo, cair
   no pai costuma converter erro em acerto.
3. **Híbrido com embedding denso** (Etapa 2) — só entra se melhorar a curva out-of-fold.
4. **`fora` conservador** — 8 exemplos não sustentam um classificador; a regra é
   abster quando não houver evidência e mandar para `revisar`.

Próximo passo: Etapa 3 (reranker) sobre o `rrf_all` e o `tfidf_char`, comparado à
regra v0 com os mesmos folds.
