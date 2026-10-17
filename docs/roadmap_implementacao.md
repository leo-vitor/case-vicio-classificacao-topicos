# Roadmap de implementação — o que foi feito e o que falta

Registro do plano em quatro fases. Estado por item: **[x]** feito, **[~]** parcial,
**[ ]** pendente (com o motivo).

Princípio preservado: **o pipeline entregue não foi alterado** (`publicacao.csv` = 222/136/1).

---

## Fase 0 — Consolidar a avaliação

| Item | Estado | Onde |
|---|---|---|
| Conferir a divergência 67% × 88% | **[x]** | `docs/avaliacao.md` §2 (são configs diferentes) |
| Métrica única (exato + hierárquico) com denominador explícito | **[x]** | `src/recuperacao.py::avaliar` |
| Separar exploração × reservado (dev/holdout) | **[x]** | `src/eval.py --split` → `outputs/avaliacao/split.csv` |
| Comando de avaliação com config, métricas, IDs de erro e versão dos dados | **[x]** | `src/eval.py` → `outputs/avaliacao/registro.csv` |
| Instrumentar tokens e latência por etapa | **[x]** | `src/uso.py` (append-only); vale das próximas execuções |

**Critério de conclusão:** atendido — os experimentos usam o mesmo conjunto, as mesmas
definições e o mesmo registro. `src/judge.py`, `fallback_arvore.py` e `verificar_arvore.py`
passaram a registrar uso.

---

## Fase 1 — Melhorar a recuperação offline

| Item | Estado | Resultado |
|---|---|---|
| Reproduzir TF-IDF atual | **[x]** | `recall_hier` 0,667 |
| TF-IDF + irmãos | **[x]** | 0,882 |
| Dicionário jurídico (referências + sinônimos) | **[x]** | `data/dicionario_juridico.csv` (62 entradas) |
| Dicionário × irmãos × ambos | **[x]** | **0,957** com ambos |
| Legislação Especial em separado | **[x]** | 5/19 → **16/19** |
| Validação dev × holdout | **[x]** | 0,952 / 0,968 (não é sobreajuste) |
| **Adotar no pipeline entregue** | **[ ]** | **não** — mudar o prompt invalida o cache do juiz (re-julgamento pago) |

**Critério de sucesso:** atendido offline (melhoria reproduzível, sem deterioração; o
holdout confirma). **Ainda não é** ganho de precisão fim-a-fim.

Documento: `docs/dicionario_juridico.md`.

---

## Fase 2 — Custo e baseline

| Item | Estado | Onde |
|---|---|---|
| Consumo por etapa e por mil questões | **[x]** | `python -m src.experimentos.custo` |
| Separar medido de projetado | **[x]** | `docs/custo_por_mil.md` |
| TF-IDF + SVM linear (baseline supervisionado) | **[x]** | `python -m src.experimentos.baseline_svm` |
| Tabela de decisão cobertura/concordância/tempo/custo | **[~]** | tabela em `docs/custo_por_mil.md` |

**Limitação do SVM (dita em voz alta):** 93 rótulos, 67 classes, 47 com 1 exemplo (70%).
Top-10 hierárquico = 0,441. Não decide arquitetura; serve de piso.

---

## Fase 3 — Irmãos: risco de gêmeo e custo

| Item | Estado | Onde |
|---|---|---|
| Medir exposição a **gêmeos** por config | **[x]** | `python -m src.experimentos.experimento_irmaos` (offline, grátis) |
| Separar ganho do **dicionário** × **irmãos** | **[x]** | `docs/irmaos_comparativo.md` §2 |
| Custo de julgar por config (tokens/questão) | **[x]** | `docs/irmaos_comparativo.md` §2–4 |
| A/B do juiz (gêmeo/revisar/concordância) | **[~]** | `python -m src.experimentos.ab_juiz --dry-run` pronto (1.092 chamadas, US$ 0,4–3); `--rodar` **gasta API** |

**Achado:** o **dicionário** (não os irmãos) é o principal motor tanto do ganho quanto da
exposição a gêmeos; `top+dic` sobe o recall com lista **menor** que a atual (mais barato),
enquanto `irmao+dic` custa ~8× de lista por +1 caso de exposição. **Recall ≠ precisão** — o
teste fim-a-fim continua pendente.

Documento: `docs/irmaos_comparativo.md`.

---

## Próximos passos (ordem sugerida)

1. **Ground truth de especialista** (destrava medir precisão de verdade).
2. Ligar o **dicionário + irmãos** num A/B **fim-a-fim** pago (o cache será invalidado):
   medir se a precisão publicada se mantém com a lista maior.
3. Confirmar o **preço vigente** dos modelos e preencher a tabela de custo.
4. Só então avaliar **embeddings privados / fine-tuning** (exigem GPU + volume de rótulos).
