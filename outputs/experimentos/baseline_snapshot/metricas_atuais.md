# Snapshot das metricas atuais

Gerado em 2026-10-16T22:24:07+00:00 (offline, sem API). Congela o estado **antes** do
experimento de dicionario no retrieval. Fonte dos numeros: `outputs/`.

## Decisoes da entrega (`publicacao.csv`)

- **publicar**: 222 (61.8%)
- **revisar**: 136 (37.9%)
- **fora**: 1 (0.3%)

## Concordancia do pipeline congelado (as duas rotulagens)

| rotulagem | publicadas | exato | hier | leniente | Wilson95 (hier) | gemeo |
|---|---|---|---|---|---|---|
| rotulos_opus | 88 | 0.7727 | 0.9205 | 0.9545 | [0.84; 0.96] | 0 |
| amostra_deepseek | 60 | 0.6667 | 0.9 | 0.9 | [0.80; 0.95] | 0 |

## Recuperacao (ultimo run por config, k=10)

### antigos_93

| config | n | recall_exato | recall_hier | cands |
|---|---|---|---|---|
| bm25+filho | 93 | 0.4731 | 0.5484 | 14.4 |
| bm25+irmao | 93 | 0.6022 | 0.7204 | 73.4 |
| rrf+filho | 93 | 0.5806 | 0.6129 | 14.2 |
| rrf+irmao | 93 | 0.6882 | 0.8172 | 75.3 |
| tfidf+filho | 31 | 0.5484 | 0.6129 | 13.4 |
| tfidf+filho+dic | 31 | 0.6774 | 0.7419 | 12.6 |
| tfidf+irmao | 31 | 0.6774 | 0.871 | 76.9 |
| tfidf+irmao+dic | 93 | 0.8495 | 0.957 | 85.9 |
| tfidf+irmao3 | 93 | 0.7204 | 0.8602 | 50.9 |
| tfidf+pai | 93 | 0.6452 | 0.6667 | 12.1 |
| tfidf+top | 93 | 0.6452 | 0.6452 | 10.0 |
| tfidf+top+dic | 31 | 0.6774 | 0.7097 | 10.0 |

### opus_148

| config | n | recall_exato | recall_hier | cands |
|---|---|---|---|---|
| bm25+filho | 148 | 0.5946 | 0.6486 | 14.5 |
| bm25+irmao | 148 | 0.6892 | 0.8041 | 76.2 |
| rrf+filho | 148 | 0.6892 | 0.75 | 14.3 |
| rrf+irmao | 148 | 0.7703 | 0.8784 | 80.2 |
| tfidf+filho | 148 | 0.7365 | 0.7905 | 13.8 |
| tfidf+filho+dic | 148 | 0.7838 | 0.8446 | 13.8 |
| tfidf+irmao | 148 | 0.8243 | 0.9257 | 83.6 |
| tfidf+irmao+dic | 148 | 0.8716 | 0.973 | 89.4 |
| tfidf+irmao3 | 148 | 0.7838 | 0.9189 | 51.8 |
| tfidf+pai | 148 | 0.7297 | 0.7905 | 12.3 |
| tfidf+top | 148 | 0.6689 | 0.75 | 10.0 |
| tfidf+top+dic | 148 | 0.7027 | 0.8041 | 10.0 |

## Plano do A/B (dry-run, gratis) — chamadas novas por config

### antigos_93

| config | novas | cache | total | tok_novos~ |
|---|---|---|---|---|
| tfidf+filho | 348 | 24 | 372 | 934,605 |
| tfidf+top+dic | 372 | 0 | 372 | 868,011 |
| tfidf+irmao+dic | 372 | 0 | 372 | 2,072,721 |

### opus_148

| config | novas | cache | total | tok_novos~ |
|---|---|---|---|---|
| tfidf+filho | 552 | 40 | 592 | 1,473,867 |
| tfidf+top+dic | 584 | 8 | 592 | 1,378,338 |
| tfidf+irmao+dic | 592 | 0 | 592 | 3,388,296 |

## Hashes dos insumos (reprodutibilidade)

- `publicacao.csv`: `6b6b9356dd7a8804`
- `outputs/candidatos.json`: `c9ef4badd83af0c4`
- `outputs/votos.jsonl`: `796bbe38919a4550`
- `outputs/votos_verificacao.jsonl`: `00019a629f6eecb1`
- `outputs/questoes_limpas.csv`: `89584264be0f73d5`
- `data/temas.csv`: `9c6e98a6cd568816`
- `data/dicionario_juridico.csv`: `4de77271944d32c4`
- `outputs/amostra_rotulagem.csv`: `472d6a3761d2f45d`
- `data/rotulos_opus.tsv`: `872fa035b44ea217`
