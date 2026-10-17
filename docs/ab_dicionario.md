# A/B: o dicionário no retrieval melhora a decisão? (não)

Teste **fim-a-fim e pago** para responder a uma pergunta simples: colocar o dicionário
jurídico na busca (`+dic`) melhora a **decisão** do pipeline, e não só o recall? Resposta:
**não** — o dicionário melhora a busca, mas o ganho não chega às publicadas.

Nada aqui altera a entrega (`publicacao.csv` permanece 222/136/1).

## Desenho do teste

- **Juiz:** `gemini-3.6-flash` + `gemini-3.1-flash-lite`, 2 rodadas cada = **4 votos/questão**,
  `TEMPERATURE=0.4`. Sem verificador dentro do A/B (o verificador é anexado na análise).
- **Rótulos:** `data/rotulos_opus.tsv` (**148 questões**, rotulagem Opus, **out-of-sample** —
  não foi usada para calibrar o dicionário).
- **Braços** (todos com cache de contexto ligado, `CONTEXT_CACHE=1`):
  - `atual` — os candidatos da entrega (âncora; com fallback da árvore inteira). 0 chamadas.
  - `tfidf+filho` — **controle limpo** (base sem dicionário, sem fallback).
  - `tfidf+filho+dic` — a **variante** (base + dicionário).
- O par científico é `tfidf+filho` × `tfidf+filho+dic` — mesma base, só o dicionário muda.
  Comparar contra `atual` confundiria (o `atual` inclui o fallback).

## Resultado no nível da decisão (Opus 148)

| Config | publicadas | concordância s/ verificador | concordância c/ verificador |
|---|---|---|---|
| `atual` (entrega) | 105 → 88 | 0,8286 (87/105) | **0,9205** (81/88) |
| `tfidf+filho` (controle) | 102 → 88 | 0,8235 (84/102) | 0,8864 (78/88) |
| `tfidf+filho+dic` (dicionário) | 103 → 89 | 0,8252 (85/103) | 0,8876 (79/89) |

**Diferença pareada `filho → filho+dic` (com verificador):** 11 decisões mudaram —
**+2 conserta, −1 quebra, 8 neutras**. Líquido: **+1 publicada correta (+0,2 pp)**.

## O dicionário *funciona* na busca — o problema é onde o ganho cai

Medindo o recall com os **mesmos rótulos Opus** (out-of-sample), pelo harness canônico
`src.eval`:

| Conjunto | `recall_hier` filho | filho+dic | Δ | adicionou o certo | perdeu |
|---|---|---|---|---|---|
| **Opus 148** (out-of-sample) | 0,791 | **0,845** | **+5,4 pp** | 9 | 1 (`Q0252`) |
| 93 (rotulagem antiga) | 0,667 | 0,763 | +9,7 pp | 9 | 0 |

Ou seja: **não é overajuste aos rótulos antigos**. No conjunto Opus o dicionário coloca o tema
certo na lista em 9 questões e derruba apenas 1. Em nível de "tema escolhido" (qualquer
decisão, com os candidatos do A/B), o pipeline vai de **96 → 106 acertos (+10)**.

Então por que a concordância das **publicadas** quase não muda? Três motivos, todos medidos:

**1. O ganho cai em `revisar`, e `revisar` não conta.** A métrica de entrega é
*publicada-e-correta*. Dos +10 acertos, **8 caem em `revisar`** (o juiz acerta o tema, mas a
agregação não publica — confiança abaixo do limiar ou rodadas divergem):

`Q0007, Q0026, Q0068, Q0165, Q0213, Q0254, Q0275, Q0309` — todas com o tema correto e todas
em revisão.

**2. O re-roteamento cancela o resto.** Mais candidatos ⇒ o juiz muda 11 decisões:
`fora→revisar` (4), `publicar→revisar` (3), `revisar→publicar` (4). Nas publicadas:
**3 viram certas, 2 viram erradas** → líquido +1.

**3. O gargalo é o juiz/agregação, não a busca.** Em `Q0184` o tema certo (4708) entrou na
lista e o juiz **mesmo assim** escolheu 5518. Nos outros 8, o juiz escolhe certo e o pipeline
manda para revisar. Quem decide entre "acertar" e "publicar" é o **limiar/agregação**, não o
recall.

## Leitura geral

- **O dicionário resolve o vocabulário** (confirma `docs/dicionario_juridico.md` no nível do
  recall), mas **não move a entrega**: o efeito na decisão é ~0 e o saldo pareado é +1.
- A **âncora `atual` é muito melhor** (0,9205 c/ verificador) que a base pura `tfidf+filho`
  (0,8864). A +3,4 pp vem do **fallback da árvore inteira** + verificador — a **vista completa**,
  não o recall.
- Ironia útil: o dicionário *compra* recall que o pipeline **já tinha** via a árvore inteira.
  As duas coisas consertam as mesmas questões; juntas, saturam.

## Custo e limitação

- ~920 chamadas novas (552 do controle + ~368 do dicionário), ordem de **~0,8 M tokens de
  entrada** — barato. (O estimador `ab_juiz.plano` infla o token por um fator
  `CHARS_POR_TOKEN=3.0`; o prompt real é ~chars/4.)
- **O braço `tfidf+top+dic` não foi executado**: os créditos de API foram esgotados
  (`402 RESOURCE_EXHAUSTED`) durante a rodada. Não muda o veredito — `top+dic` é uma variante
  de retrieval, e o problema demonstrado é que o ganho de retrieval não chega à decisão.
- **Cache de contexto:** ligado e validado (16.874/17.234 tokens de entrada vieram do cache,
  ~98%). É recomendação de produção, mas **o desconto em preço não foi confirmado** — só os
  tokens foram medidos.

## Veredito e recomendação

- **Não adotar o dicionário no retrieval.** O ganho de decisão (~+0,2 pp, 1 questão) não
  justifica trocar as listas (invalida o cache do juiz e implica uma rodada quase inteira).
- **Manter o cache de contexto** como recomendação de produção (custo ↓, mesma qualidade).
- **Próximo passo com mais orçamento:** não é mais retrieval — é o **verificador de outra
  família** (ataca o erro correlacionado/unânime, que é o que sobra).

## Reprodução (offline, sem API)

```bash
# análise pareada a partir dos votos já gravados (com/sem verificador)
.venv/bin/python -m src.experimentos.ab_dic --rotulos data/rotulos_opus.tsv \
    --configs atual tfidf+filho tfidf+filho+dic --par tfidf+filho tfidf+filho+dic

# recall por conjunto (usa os candidatos das variantes)
.venv/bin/python -m src.eval --config tfidf+filho+dic --rotulos data/rotulos_opus.tsv
```

Votos em `outputs/experimentos/ab_juiz/<config>_rotulos_opus.votos.jsonl`; análise em
`outputs/experimentos/ab_juiz/analise_rotulos_opus.json`.
