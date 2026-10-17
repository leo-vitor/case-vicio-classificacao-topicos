# Custo por mil questões (Fase 2)

Separa **o que foi medido** de **o que é projeção**. Preço não é inventado: sem a tabela
vigente, mostramos tokens. Comando: `python -m src.experimentos.custo`.

## Medido (último run do juiz — `outputs/uso.json`)

| Item | Valor |
|---|---|
| Chamadas novas | 112 |
| Do cache | 1.324 |
| Questões cobertas no run | 1.436 / 4 votos = **359** |
| Tokens de entrada | 945.992 |
| Tokens de saída | 9.188 |
| Tokens de raciocínio | 30.660 |
| Tempo | 89,1 s |
| Por chamada (média) | ~8.446 in / 82 out / 274 pensando |

**Ressalva honesta:** as 112 chamadas novas foram as do **fallback** (prompt com a árvore
inteira) → a média por chamada é **alta** e **superestima** um run típico. É um teto, não
uma média representativa.

As etapas `fallback_arvore` e `verificar_arvore` **não registravam** uso; agora registram
(`outputs/uso_etapas.jsonl`), mas isso vale das **próximas** execuções. O custo da
verificação já feita permanece **não documentado** — e não é estimado aqui.

## Projeção (rotulada como projeção)

| Volume | Entrada | Saída |
|---|---|---|
| 1.000 questões | ~33,8 M tokens | ~0,33 M tokens |
| 50.000 questões/semana | ~1.689 M tokens | ~16,4 M tokens |

(4 votos por questão, a partir da média medida. É extrapolação, não medição.)

## Custo por abordagem

| Abordagem | Custo de API | Precisão/recall observado |
|---|---|---|
| Retrieval local (TF-IDF / dicionário / irmãos) | **0** | recall_hier 0,914 (k=10) |
| SVM linear local (Fase 2) | **0** | top-10 hier 0,441 |
| Juiz LLM (4 votos) | medido acima | precisão observada 0,90 (publicadas) |

Para informar custo em dinheiro, defina as variáveis e rode `python -m src.experimentos.custo`:

```
GEMINI_PRECO_IN_POR_MILHAO=<valor> GEMINI_PRECO_OUT_POR_MILHAO=<valor> python -m src.experimentos.custo
```

## Baseline supervisionado (TF-IDF + SVM linear)

`python -m src.experimentos.baseline_svm` (leave-one-out, régua do case):

| k | exato | hierárquico |
|---|---|---|
| 1 | 0,204 | 0,237 |
| 3 | 0,376 | 0,387 |
| 5 | 0,419 | 0,430 |
| 10 | 0,430 | 0,441 |

**Limitação central:** 93 rótulos para 67 classes, **47 delas com um único exemplo** (70%).
Com esses dados, um classificador linear **não** é confiável e **não** deve escolher a
arquitetura. Serve como **piso** de comparação — e mostra que o ganho real está na
**recuperação + juiz**, não num classificador supervisionado com poucos rótulos.

## Conclusão (tabela de decisão)

- A parte **local e gratuita** (recuperação) resolve o gargalo de busca (recall 0,914) sem
  API. Vale sempre, e não depende de fornecedor.
- O **juiz de fronteira** continua necessário para a decisão, mas é onde está o custo.
- Um **embedding privado/treinado** só se justifica com **GPU + volume de rótulos** — hoje
  não supera a opção lexical + estrutural (ver `docs/metodologia_avaliacao.md`, seção 6).
