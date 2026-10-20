# Avaliação de recuperação — método único e reproduzível (Fase 0)

Este documento fixa **como medimos a recuperação** e resolve a divergência de números
que aparecia entre experimentos. Comando canônico: `python -m src.eval`.

Nada aqui altera o pipeline entregue (`publicacao.csv` permanece 222/136/1).

## 1. Métricas e denominador

Régua do case: acerto = tema **atribuído, pai ou filho direto**. **Irmão não conta.**

| Métrica | Definição |
|---|---|
| `recall_exato` | o próprio `tema_correto_id` está na lista de candidatos |
| `recall_hier` | algum candidato é o tema, o pai ou o filho direto (basta para o juiz acertar) |
| `recall_via_pai` | o tema só entrou porque o **pai** foi recuperado (subconjunto de `recall_hier`) |

**Denominador explícito:** `n` = número de questões rotuladas avaliadas (93 no total;
ou o tamanho do subconjunto dev/holdout). Nunca misturamos denominadores.

## 2. Por que apareciam "67%" e "88%" ao mesmo tempo

Não é contradição: são **configurações diferentes**, e ambas saem do mesmo harness:

| Número | O que é |
|---|---|
| **0,667** | `tfidf + filho` (a configuração **atual**) @ k=10, `recall_hier` |
| **0,882** | `tfidf + irmãos` @ k=10, `recall_hier` |
| **0,946** | `tfidf + irmãos` @ k=30 |
| **0,645** | `tfidf + top` (sem expansão) @ k=10, `recall_hier`/`exato` |
| **0,882** | valor do `candidatos.json` pós-fallback — **inflado** (parte das questões recebeu a árvore inteira); não é comparável 1:1 |

Ou seja: **67% = configuração atual**; **88% = configuração melhorada** (irmãos). O harness
padroniza as duas na mesma definição e no mesmo conjunto.

## 3. Conjunto de avaliação: exploração × reservado

`python -m src.eval --split` cria `outputs/avaliacao/split.csv`, **estratificado por
disciplina** e determinístico (seed 42):

| Disciplina | dev (exploração) | holdout (comparação) |
|---|---|---|
| Penal | 27 | 14 |
| Processo Penal | 15 | 8 |
| Direito Penal - Legislação Especial | 13 | 6 |
| Criminologia | 7 | 3 |
| **Total** | **62** | **31** |

Regra: o **holdout** serve para confirmar; só olhamos ele depois de escolher a ideia no dev.

## 4. Resultado canônico (k=10)

Todos os 93 rótulos (`--sweep`):

| Config | `recall_exato` | `recall_hier` | cands médios | Legislação Especial |
|---|---|---|---|---|
| tfidf+top | 0,645 | 0,645 | 10,0 | 5/19 |
| tfidf+pai | 0,645 | 0,667 | 12,1 | 5/19 |
| **tfidf+filho (atual)** | 0,645 | **0,667** | 14,1 | 5/19 |
| tfidf+irmao3 | 0,720 | 0,860 | 50,9 | 7/19 |
| tfidf+irmao | 0,753 | 0,882 | 80,2 | 9/19 |
| tfidf+filho+dic | 0,731 | 0,763 | 14,0 | 12/19 |
| tfidf+top+dic | 0,720 | 0,731 | 10,0 | 12/19 |
| **tfidf+irmao+dic** | **0,849** | **0,957** | 85,9 | **16/19** |
| bm25+filho | 0,473 | 0,548 | 14,4 | 1/19 |
| bm25+irmao | 0,602 | 0,720 | 73,4 | 3/19 |
| rrf+filho | 0,581 | 0,613 | 14,2 | 2/19 |
| rrf+irmao | 0,688 | 0,817 | 75,3 | 6/19 |

Restam **4 erros** na melhor config (`Q0114, Q0181, Q0298, Q0333`). Dicionário na versão
`4de77271944d` (62 entradas).

**Validação em dev × holdout** (confirma que o ganho não é sobreajuste):

| Config | dev `recall_hier` (62) | holdout `recall_hier` (31) |
|---|---|---|
| tfidf+filho | 0,694 | 0,613 |
| tfidf+filho+dic | 0,774 | 0,742 |
| tfidf+top+dic | 0,742 | 0,710 |
| tfidf+irmao | 0,887 | 0,871 |
| **tfidf+irmao+dic** | **0,952** | **0,968** |

Leitura: o **dicionário** sobe o piso (até sem irmãos) e, combinado com **irmãos**, leva a
Legislação Especial de 2/6 para **6/6** no holdout. O ganho **se mantém** fora do dev.
Wilson 95%: holdout 30/31 = [0,84; 0,99]; dev 59/62 = [0,87; 0,98] — o holdout é pequeno
(1 questão = 3,2 p.p.), então os intervalos são largos.

## 5. Comando e registro

```
python -m src.eval --split                       # cria dev/holdout (uma vez)
python -m src.eval --config tfidf+irmao+dic --k 10
python -m src.eval --sweep                        # bateria principal
python -m src.eval --config tfidf+irmao+dic --conjunto holdout
```

Cada execução grava:

- `outputs/avaliacao/runs/<run_id>.json` — configuração, métricas, **IDs dos erros**,
  por-disciplina, latência e a **versão dos dados** (hashes de `questoes_limpas`,
  `amostra_rotulagem`, `temas` e do dicionário);
- `outputs/avaliacao/registro.csv` — uma linha por execução (tabela comparável).

`run_id` = `AAAAmmddTHHMMSS_<config>_k<k>_<conjunto>`. Duas execuções com o mesmo
`dados_questoes` e `dic_versao` são comparáveis; se a versão mudar, o número muda.

## 6. Instrumentação de uso (tokens e latência)

`src/judge.py` já gravava `outputs/uso.json`, mas **sobrescrevia** a cada run e as etapas
`fallback_arvore` e `verificar_arvore` **não gravavam nada**. Agora `src/uso.py` mantém um
log **append-only**:

- `outputs/uso_etapas.jsonl` — uma linha por execução de etapa (tokens, chamadas, segundos);
- `python -m src.uso` imprime o resumo somado por etapa;
- `python -m src.experimentos.custo` calcula o consumo por 1.000 questões (ver `docs/custo_por_mil.md`).

Valores **não medidos** ficam `null` — não estimamos o que não foi registrado.

## 7. Limitações (valem para todo número acima)

- Recall é **condição necessária**, não prova de ganho fim-a-fim: uma lista ~5× maior
  pode confundir o juiz. A precisão publicada só se mede com o juiz rodando de novo.
- Os rótulos são assistidos por IA (DeepSeek): a métrica é **concordância**, não verdade.
- Adotar isso no pipeline muda o prompt e **invalida o cache** do juiz → re-julgamento pago.
