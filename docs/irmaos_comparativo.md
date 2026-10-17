# Irmãos valem a pena? Risco, gêmeos e custo (Fase 3)

Responde a uma pergunta só: **acrescentar "irmãos" à recuperação compensa**, levando em
conta (1) risco de piorar a classificação, (2) risco de confundir com um **tema gêmeo** e
(3) o **custo extra** de julgar mais candidatos.

Tudo aqui é **offline, reprodutível e sem API** — exceto o teste pago no fim, que fica
**pronto para rodar** mas não foi executado.

Comandos:

```
.venv/bin/python -m src.experimentos.experimento_irmaos                 # recall + gêmeos + custo (grátis)
.venv/bin/python -m src.experimentos.ab_juiz --dry-run                  # A/B: conta chamadas e estima custo (grátis)
.venv/bin/python -m src.experimentos.ab_juiz --rodar                    # A/B de verdade (GASTA API)
```

Artefatos: `outputs/experimentos/irmaos/` (resumo/por_questao por conjunto) e
`outputs/experimentos/ab_juiz/` (plano.json).

## 1. Veredito curto

- **O ganho de recall vem sobretudo do dicionário, não de irmãos.** `top+dic` mantém a
  lista em ~10 e sobe `recall_hier` de 0,667 → 0,731; irmãos só (sem dicionário) chegam a
  0,882, mas com uma lista **5,2× maior**.
- **O risco de gêmeo também é dirigido pelo dicionário, não por irmãos.** A exposição
  (o gêmeo *do tema correto* aparecer na lista) sobe de **4** para **9** com `top+dic`
  (lista do mesmo tamanho) e só chega a **10** com `irmao+dic` (lista **5,6×**). Ou seja,
  irmãos gastam ~8× a lista para comprar **+1** caso de exposição.
- **Melhor custo-benefício do bloco: `top+dic`.** Mesma lista da entrega (10 vs 14) →
  **mais barato** que a config atual, com mais recall e Legislação Especial 12/19 (vs 5/19).
- **`irmao+dic` é o maior recall** (0,957), **mas é o maior risco e custo** e **não deve ser
  adotado** antes do A/B pago (seção 5). Recall não é precisão.

## 2. Recuperação, risco de gêmeo e custo (93 rotuladas, k=10)

`recall_hier` = tema, pai ou filho direto na lista. "gêmeo do correto" = quantas questões
têm na lista o **gêmeo do tema certo** (mesmo título, raiz diferente) — a oportunidade de
confusão. Custo = tamanho do bloco de candidatos (o único trecho do prompt que muda).

| config | `recall_hier` | cands | Leg. Esp. | gêmeo do correto | correto **+** gêmeo | lista ×atual | Δtok/questão* |
|---|---|---|---|---|---|---|---|
| `tfidf+top` | 0,645 | 10,0 | 5/19 | 4 | 4 | 0,73 | −324 |
| **`tfidf+filho` (atual)** | 0,667 | 14,1 | 5/19 | 4 | 4 | 1,00 | 0 |
| **`tfidf+top+dic`** | 0,731 | 10,0 | 12/19 | **9** | 9 | **0,73** | **−316** |
| `tfidf+filho+dic` | 0,763 | 14,0 | 12/19 | 9 | 9 | 1,00 | −4 |
| `tfidf+irmao` | 0,882 | 80,2 | 9/19 | 8 | 6 | 5,18 | +4.932 |
| **`tfidf+irmao+dic`** | **0,957** | 85,9 | **16/19** | **10** | 10 | 5,61 | **+5.440** |

\* tokens de **entrada por questão** (4 votos), relativo à config atual; proxy `chars/3`
do próprio repo (teto, não média). Confirmado no holdout (31): `filho` 0,613 → `top+dic`
0,710 → `irmao+dic` 0,968; gêmeo-do-correto 1 → 4 → 4.

**Temas gêmeos na árvore:** 16 (de ~375). Rotuladas cujo tema correto é gêmeo: **12/93**
(4/31 no holdout). A exposição nunca some: as duas cópias têm **título idêntico**, então
qualquer ampliação de lista as puxa juntas.

## 3. Leitura dos três riscos

**(1) Piorar a classificação.** Não medido sem o juiz. O que se sabe: mais candidatos
corretos = mais chance de o juiz acertar, mas lista maior também pode confundir. Métricas de
recuperação são **monotônicas** — não detectam esse risco. Só o A/B (seção 5) responde.

**(2) Confundir com gêmeo.** Medido como **exposição** (oportunidade), não erro. O ponto
novo: **não é o irmão que injeta gêmeos** (gêmeos têm pais diferentes, logo não são irmãos
na árvore); é o **tamanho/amplitude da lista**, e o dicionário já produz isso sozinho
(4 → 9, com lista de 10). O `src/decide.py` já tem uma rede: se o tema publicado é gêmeo e
a raiz ≠ disciplina de origem, vai para `revisar`. Ou seja, o efeito provável de ampliar a
lista é **perder cobertura**, não publicar errado — mas isso precisa ser confirmado.

**(3) Custo extra.** Índice de custo (4 votos/questão, teto):

| config | Δ tok/questão vs atual | Δ US$/1.000 (a US$ 0,30/M) | Δ US$/1.000 (a US$ 0,75/M) |
|---|---|---|---|
| `tfidf+top+dic` | −316 | −US$ 0,09 | −US$ 0,24 |
| `tfidf+irmao` | +4.932 | +US$ 1,48 | +US$ 3,70 |
| `tfidf+irmao+dic` | +5.440 | +US$ 1,63 | +US$ 4,08 |

## 4. Custo por mil questões (medido × faixa de preço)

**Medido** (`outputs/uso.json`, último run do juiz): 112 chamadas novas, 945.992 tokens de
entrada, 9.188 de saída, 30.660 de raciocínio; ~8.446 tokens de entrada/chamada. Projeção do
repo: **~33,8 M tokens de entrada / 1.000 questões** (4 votos).

| preço (in / out por M)* | por questão | por 1.000 | 50 mil/semana |
|---|---|---|---|
| US$ 0,10 / 0,40 (Flash-Lite) | US$ 0,0035 | **US$ 3,51** | US$ 176 |
| US$ 0,30 / 2,50 (Flash médio) | US$ 0,0110 | **US$ 10,96** | US$ 548 |
| US$ 0,75 / 3,75 (Flash topo) | US$ 0,0266 | **US$ 26,57** | US$ 1.329 |

\* tabela pública de out/2026 — **verificar no contrato**; há sinal de **dobra em 01/01/2027**.
Números gerados por `python -m src.experimentos.custo` (com `GEMINI_PRECO_IN_POR_MILHAO`/`_OUT_`). O
`src/custo.py` usa só a saída "visível"; os **tokens de raciocínio** também são cobrados como
saída, então o custo real é **um pouco maior** que a tabela. O run medido é do
**fallback** (prompt com a árvore inteira) → é **teto**, não média representativa.

**Custo-benefício.** A parte que mais decide (recuperação local) é **grátis** e leva o
`recall_hier` a 0,957. O custo está no juiz. Como o **dicionário sozinho** (com lista
pequena) já entrega o essencial por **menos** que a config atual, e irmãos custam ~8× de
lista por ganho marginal de exposição, a aposta de melhor custo-benefício é
**`tfidf+top+dic`** — não irmãos.

**Não medido (e por isso não estimado):** o uso do **verificador** (235–261 votos) e do
**fallback** já realizado nunca foi registrado (`src/uso.json`). O custo acumulado do
projeto é **maior** que a tabela; a instrumentação vale das próximas execuções.

## 5. O teste que falta (pronto, não executado)

`src/ab_juiz.py` re-julga as 93 rotuladas com o **mesmo juiz** e as **mesmas regras**, em 3
configs (`filho`, `top+dic`, `irmao+dic`), e mede: **publicar/revisar/fora**, **concordância
nas publicadas**, **escolha de gêmeo** e **rebaixamentos por gêmeo**.

`--dry-run` (já rodado): **1.092 chamadas novas**, ~3,9 M tokens de entrada (teto) →
**~US$ 0,4 a 3**. Protegido para não gastar por engano (default é dry-run; o juiz real só
com `--rodar`).

Como ler o resultado:

| resultado | leitura |
|---|---|
| juiz nunca escolhe o gêmeo e concordância não cai | exposição **inerte**; `top+dic` liberado |
| escolhe o gêmeo → vira `revisar` | custo é **cobertura**; quantificar |
| publica o gêmeo | risco real de precisão → bloqueia `irmao+dic` |

## 6. Por que Gemini

**Honestidade primeiro:** a escolha foi por **familiaridade com a API**, não por benchmark.
O que ela **de fato** compra nesta implementação:

- **Modo JSON nativo** (`response_mime_type="application/json"`) — o juiz devolve
  `tema_central_id/extras_ids/confianca/motivo` estruturado, sem parsing frágil.
- **Vários tiers baratos na mesma chave** → o *ensemble* (`gemini-3.6-flash` +
  `gemini-3.1-flash-lite`) e o verificador saem sem trocar de fornecedor.
- **Contexto longo** — o fallback manda a árvore inteira (~375 temas) numa chamada só.
- **Cache de contexto** (desconto grande) — o prefixo da árvore repete em toda questão;
  ganho estrutural ainda **não ativado**.
- **Tokens de raciocínio + `usage_metadata`** — base da contabilização de custo por etapa.

**Onde a justificativa é fraca (limitações):** o *ensemble* é **single-vendor** (erros
correlacionados); **não houve A/B** contra OpenAI/Claude/Gemini mais barato; há **lock-in** e
**risco de dobra de preço em 2027**. Para
justificar de verdade: comparar 1–2 alternativas em **concordância × custo** no mesmo
conjunto. Enquanto isso, Gemini é **defensável**, não **demonstrado**.

## 7. Limitações

- Rótulos são assistidos por IA (DeepSeek) → mede-se **concordância**, não precisão.
- "Gêmeo" medido aqui é **exposição** (estar na lista), não erro do juiz.
- Proxy de token `chars/3` é **teto** (arvore inteira: 8.894 no proxy vs 8.446 medidos).
- Verificador e fallback **sem uso registrado**; custo acumulado **maior** que o medido.
- Nada disso altera `publicacao.csv` (222/136/1), que permanece congelado.
