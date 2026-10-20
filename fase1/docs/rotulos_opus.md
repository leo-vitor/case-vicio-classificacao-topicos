# Nova rotulagem (Opus) — o pipeline se sustenta?

Testes recriados sobre uma **rotulagem nova e independente** (`data/rotulos_opus.tsv`,
150 questões) para checar se o que concluímos com os 93 rótulos antigos **se reproduz**.

Tudo **offline, sem API**, exceto o A/B do juiz no fim (**executado em parte**; ver seção 5).

```
.venv/bin/python -m src.experimentos.avaliacao_pipeline --rotulos data/rotulos_opus.tsv   # pipeline congelado
.venv/bin/python -m src.eval --sweep --rotulos data/rotulos_opus.tsv         # recuperacao por config
.venv/bin/python -m src.experimentos.experimento_irmaos --rotulos data/rotulos_opus.tsv   # gemeo + custo
.venv/bin/python -m src.experimentos.ab_juiz --dry-run --rotulos data/rotulos_opus.tsv    # A/B (pago, so conta)
```

## 0. O que é a nova rotulagem

| Coluna | Significado |
|---|---|
| `tema_id` | tema considerado correto (148/150 preenchidos) |
| `fora` | 0 em todas — são todas questões de escopo |
| `duvida` | baixa (64), média (48), alta (38) — **confiança do próprio rotulador** |
| `multitema` | 1 para 21 questões |
| `alternativo` | 2º tema aceitável, preenchido em 103 |
| `base_legal`, `nota` | justificativa |

**Sobreposição com os 93 rótulos antigos: 41 questões.** Acordo nesse subconjunto:
**0,54 exato** e **0,85 tema/pai/filho**. Ou seja, as duas rotulagens concordam no
"ramo", mas discordam muito no "tema exato" — **a conclusão é sensível a quem rotula.**

## 1. Pipeline congelado × rotulagem nova (o teste mais importante)

`publicacao.csv` **não foi tocado**; só o comparamos com os 148 rótulos casados.

| Decisão | n | Concordância **hierárquica** (tema/pai/filho) | Exata | Leniente¹ |
|---|---|---|---|---|
| **publicar** | 88 | **0,921** | 0,773 | 0,955 |

¹ leniente = também aceita o campo `alternativo`.

- **A concordância ~0,90 se reproduz** numa rotulagem independente (0,92 hier, n=88).
- **Escolhas de gêmeo: 0.** O medo de publicar o gêmeo errado **não se materializou** aqui
  (26/148 rótulos apontam para um tema gêmeo, e ainda assim zero erro desse tipo).
- **Onde erram:** entre as 60 não publicadas, o tema correto era **recuperável em 46** e a
  sugestão já estava certa em **31** — há espaço para publicar mais sem inventar.

**Por `dúvida` do rótulo** (nas publicadas) — o erro segue a incerteza do rotulador:

| dúvida | n | hier | exata |
|---|---|---|---|
| baixa | 45 | **1,00** | 0,978 |
| média | 32 | 0,875 | 0,594 |
| alta | 11 | **0,727** | 0,455 |

## 2. Recuperação por configuração (148 rótulos novos, k=10)

| config | exato | `recall_hier` | cands | Leg. Esp. |
|---|---|---|---|---|
| `tfidf+top` | 0,669 | 0,750 | 10,0 | 16/28 |
| `tfidf+filho` (**atual**) | 0,736 | 0,791 | 13,8 | 16/28 |
| `tfidf+top+dic` | 0,703 | 0,804 | 10,0 | 22/28 |
| `tfidf+filho+dic` | 0,784 | 0,845 | 13,8 | 22/28 |
| `tfidf+irmao` | 0,824 | 0,926 | 83,6 | 18/28 |
| **`tfidf+irmao+dic`** | **0,872** | **0,973** | 89,4 | **25/28** |
| `bm25+filho` | 0,595 | 0,649 | 14,5 | 10/28 |
| `rrf+irmao` | 0,770 | 0,878 | 80,2 | 13/28 |

O ranking das configs **se replica**: dicionário sobe o piso, irmãos sobem o topo, e a
melhor continua sendo `irmao+dic` (0,973). Os 4 erros residuais da config antiga já não
são os mesmos — isso é a troca de rotulador, não de modelo.

## 3. Gêmeo × custo (148 rótulos novos)

| config | `recall_hier` | cands | Leg. Esp. | gêmeo do correto | correto+gêmeo | lista× | Δtok/questão |
|---|---|---|---|---|---|---|---|
| `tfidf+top+dic` | 0,804 | 10,0 | 22/28 | **21** | 21 | **0,75** | **−284** |
| `tfidf+filho` (atual) | 0,791 | 13,8 | 16/28 | 14 | 14 | 1,00 | 0 |
| `tfidf+irmao` | 0,926 | 83,6 | 18/28 | 21 | 18 | 5,51 | +5.220 |
| `tfidf+irmao+dic` | 0,973 | 89,4 | 25/28 | **23** | 22 | 5,97 | **+5.752** |

**O achado do estudo anterior se confirma:** é o **dicionário** (14 → 21), não os irmãos
(21 → 23), que puxa a exposição a gêmeos — e ele faz isso **com lista menor que a atual**
(`top+dic`, 0,75×, mais barato). Irmãos gastam **~6× a lista** por **+2** casos.

Custo por 1.000 questões (medido, seção 4 de `docs/irmaos_comparativo.md`):
**US$ 3,51 / 10,96 / 26,57** em três faixas de preço. `irmao+dic` adiciona ~US$ 1,7–4,3/1.000.

## 4. Leitura

- **Boa notícia:** a concordância publicada (~0,92) **reproduz** fora da amostra, e **não
  houve escolha de gêmeo** — a rede do `decide.py` parece suficiente nesse conjunto.
- **Ruído de rótulo:** 0,54 de acordo exato entre dois rotuladores é **alto**. Qualquer
  número de "precisão" aqui é, de fato, **concordância com um rotulador específico**.
- **Decisão de configuração não muda:** `top+dic` continua o melhor custo-benefício;
  `irmao+dic` continua o teto de recall com o maior custo e a maior exposição.

## 5. O A/B pago (executado em parte)

> **Atualização.** O A/B **foi executado** para `tfidf+filho` e `tfidf+filho+dic`; o braço
> `top+dic` ficou de fora (créditos de API esgotados, 402). Resultado e veredito em
> `docs/ab_dicionario.md` (o ganho de retrieval não chega à decisão). O `--dry-run` para as
> 148 contava **~1.728 chamadas novas** na época; hoje o cache cobre a maior parte (~1.148).

`python -m src.experimentos.ab_juiz --rodar --rotulos data/rotulos_opus.tsv` (só com `--rodar`)
re-julgaria `filho` / `top+dic` / `irmao+dic` com juiz real, para medir se a lista maior
**mantém** a concordância e se aparece alguma escolha de gêmeo.

## 6. Limitações

- Rotulagem **assistida por IA** (Opus) → mede **concordância**, não precisão.
- `alternativo` foi interpretado como **2º tema aceitável** (convenção assumida).
- Métricas de recuperação são **monotônicas**: não provam ganho fim-a-fim.
- Nada aqui altera `publicacao.csv` (222/136/1), que segue congelado.
