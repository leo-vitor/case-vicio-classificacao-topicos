# src/experimentos

Módulos de experimentação. **Nenhum** faz parte da entrega (`publicacao.csv`); são
opt-in e rodam à parte. O núcleo de produção fica em `src/` (clean, candidates,
expandir_fora, fallback_arvore, judge, verificar_arvore, decide, validate, eval).

| Módulo | O que é |
|---|---|
| `eval.py` (em `src/`) | Avaliação **canônica** de recuperação (`python -m src.eval`). Importado por vários experimentos — por isso fica no núcleo. |
| `experimento_irmaos.py` | Irmãos × risco de gêmeo × custo (offline, grátis). |
| `ab_juiz.py` | A/B do juiz entre configs de recuperação (`--dry-run` grátis; `--rodar` gasta API). |
| `ab_dic.py` | Analisa o A/B já pago (decisão com/sem verificador, LegEsp, diferença pareada). Offline. |
| `avaliacao_pipeline.py` | Pipeline congelado × rotulagem nova (offline). |
| `classificador.py` | Classificador treinado (TF-IDF + regressão logística); piso de comparação. |
| `baseline_svm.py` | Baseline supervisionado (TF-IDF + SVM linear). |
| `audit.py` | Auditoria offline (recall, erros, votos, Dawid-Skene). |
| `seletiva.py` | Política seletiva testada e **não adotada**. |
| `recall_recuperacao.py` | Experimento histórico de recuperação; superado por `src.eval`, mantido por rastreabilidade. |
| `snapshot_metricas.py` | Congela todas as métricas atuais em `outputs/experimentos/baseline_snapshot/`. |
| `custo.py` | Consumo por etapa e projeção por 1.000/50.000 questões. |

Rode sempre como módulo a partir da raiz do repositório, p.ex.:

```bash
.venv/bin/python -m src.experimentos.ab_dic --rotulos data/rotulos_opus.tsv \
    --configs atual tfidf+filho tfidf+filho+dic --par tfidf+filho tfidf+filho+dic
```
