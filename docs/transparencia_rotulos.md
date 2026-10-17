# Transparência: como os rótulos da amostra foram produzidos

Esta página existe porque parte da avaliação de precisão usa rótulos que **não
vieram dos especialistas do case**. Sem registrar isso, o `previsao.txt` daria a
entender que existe um gabarito humano.

## Declaração

| Campo | Valor |
|---|---|
| Modelo usado para rotular | **DeepSeek** |
| Data(s) da rotulagem | outubro/2026 |
| Prompt usado | não arquivado neste repositório |
| O rotulador viu o `assunto_origem`? | não registrado |
| O rotulador viu a saída do modelo (`publicacao.csv`/`votos.jsonl`)? | não registrado (não confirmado) |
| Quantas questões foram rotuladas por IA | 93 |
| Dessas, quantas estavam publicadas na base | 68 |
| Dessas, quantas continuam publicadas após o verificador | 60 |
| Quantas foram revisadas por especialista humano | 0 |
| Quantas foram adjudicadas (não especialista) | 6 (`docs/adjudicacao_erros.csv`) |
| Como divergências IA × humano foram resolvidas | não houve adjudicação por especialista; os 6 desacordos têm parecer de assistente não especialista, com grau de certeza |

### Segunda rotulagem (checagem)

| Campo | Valor |
|---|---|
| Modelo usado | **Opus** |
| Data | outubro/2026 |
| Quantas questões | 150 (148 com tema) |
| O rotulador viu a saída do modelo? | não registrado; 41 questões coincidem com o conjunto do DeepSeek |
| Papel | checagem "quase fora da amostra" da primeira rotulagem |
| Rótulos | `data/rotulos_opus.tsv` |

As duas rotulagens não são independentes entre si (41 questões em comum) e nenhuma
é gabarito humano; a concordância entre elas é 0,85 na régua pai/filho.

## Uso de IA na própria entrega

O **código, este relatório e o memo** foram escritos com assistência de IA (um agente
de codificação). O desenho do pipeline, a adjudicação dos erros e a leitura dos
resultados são do autor. O case permite o uso de IA; o julgamento é do autor, que
assina as afirmações.

## Por que isso importa

1. **Concordância não é verdade.** Comparar o rótulo de uma IA com a resposta de
   outro LLM mede correlação entre modelos, não acerto contra o gabarito.
2. **Viés de família.** O rotulador (DeepSeek) é de família diferente do juiz
   (Gemini), o que é mais honesto do que rotular com o próprio juiz, mas **ainda
   não é gabarito**. A precisão medida permanece desconhecida.
3. **Sem especialista, não há garantia formal.** A avaliação dá um alvo
   defensável, mas não uma garantia de 95% sobre a população. O relatório e o
   `previsao.txt` dizem isso de forma explícita.

## Convenções de rotulagem usadas

- `tema_correto_id` recebe o id do tema no nível mais específico que o enunciado
  permite.
- A régua de acerto é a do case: **mesmo tema, pai ou filho direto**; irmãos sob
  o mesmo pai contam como **erro**.
- `fora` quando nenhum tema da árvore serve (ex.: questão de outra área).
- `incerto = 1` quando havia mais de um tema defensável.

## Rastreabilidade

- Rótulos: `outputs/amostra_rotulagem.csv` (coluna `fonte` indica a origem).
- Adjudicação dos desacordos: `docs/adjudicacao_erros.csv`.
- Grupos (não abrir durante a rotulagem): `outputs/amostra_grupos.csv`.
- Vários anotadores (quando houver): `outputs/rotuladores.csv` →
  `python -m src.experimentos.audit latente` estima a confiabilidade de cada anotador **sem
  gabarito** (modelo latente *one-coin*, Dawid & Skene, 1979; Raykar et al., 2010).
