# Auditoria do verificador e da contagem final

Fonte: `outputs/publicacao_congelada.csv` (base, 261 publicadas),
`outputs/votos_verificacao.jsonl` (261 votos) e `publicacao.csv` (final, 222
publicadas). Script de conferência: `python -m src.validate` e as contagens abaixo.

## Da base à entrega final

| Passo | Publicadas |
|---|---|
| Pipeline antes da verificação (`publicacao_congelada.csv`) | **261** |
| Concordâncias do verificador com o tema publicado | 225 |
| Discordâncias do verificador | 36 |
| Rebaixadas pela discordância (36) | 36 |
| Rebaixadas por reavaliação das regras de agregação (5º voto muda score/kind) | 3 |
| Total rebaixado | 39 |
| **Publicação final (`publicacao.csv`)** | **222** |

A diferença entre 225/261/222: o verificador **concordou em 225**, **discordou em
36**; as 36 discordâncias foram rebaixadas, e mais **3** questões foram rebaixadas
porque o voto extra mudou a agregação (não a comparação direta de tema). As 3 são
`Q0242`, `Q0151`, `Q0153`. Assim, 261 − 39 = 222.

Observação: o número de rebaixamentos (39) **não** é igual ao número de
discordâncias (36). Relatórios devem citar os dois números separadamente.

## Desempenho do verificador na amostra rotulada

Critério adotado para o verificador, **definido antes de rodar**: vetar ao menos
**3 erros reais**, com no máximo **20% de vetos falsos**. Resultado: **5 erros
vetados** (≥ 3) e **3/57 = 5% de vetos falsos** (≤ 20%) — dentro do critério.

Das 261 publicadas, 68 tinham rótulo. A matriz (rótulo × verificador):

| | verificador concorda | verificador discorda |
|---|---|---|
| publicada **certa** | 54 | **3 (falsos vetos)** |
| publicada **errada** | **6 (erros não pegos)** | **5 (erros pegos)** |

- **Erros pegos (5):** `Q0076`, `Q0158`, `Q0064`, `Q0249`, `Q0284`.
- **Erros não pegos (6):** `Q0120`, `Q0085`, `Q0273`, `Q0306`, `Q0016`, `Q0238`.
- **Falsos vetos (3):** `Q0324`, `Q0094`, `Q0290`.

Das 68 rotuladas publicadas, 8 foram rebaixadas: 5 erradas (ganho) e 3 certas
(custo de cobertura). O verificador usa a **mesma família** do juiz
(`gemini-3.1-flash-lite` verificando votos de `gemini-3.6-flash`/`-flash-lite`),
então os erros dos dois podem ser correlacionados — 6 erros passaram pelo
verificador, inclusive `Q0120`, que trata de resposta à acusação e foi para
"Teoria Geral das Provas".

## Uso e custo da etapa de verificação

`src/verificar_arvore.py` **não persiste** o uso: ao final imprime `J.STATS` (em
memória) e não grava arquivo. Os caches (`outputs/cache/judge/*.json`) guardam
apenas o texto da resposta, sem contagem de tokens. Por isso:

- **Documentado:** 261 votos em `outputs/votos_verificacao.jsonl`.
- **Não documentado:** número de chamadas novas e tokens da verificação.

Não há, portanto, custo de tokens da verificação para somar de forma confiável; o
valor não é estimado aqui. Ver `outputs/uso.json` para o escopo do que foi gravado.

## Limites desta auditoria

- O "erro" é medido contra rótulos assistidos por IA (DeepSeek), nos 68 casos
  rotulados; é concordância, não verdade.
- Amostra pequena: 3 falsos vetos em 57 certas é compatível com uma taxa real
  bem maior.
- O verificador só é acionado sobre as publicadas; não avalia as que já estavam
  em revisão.
