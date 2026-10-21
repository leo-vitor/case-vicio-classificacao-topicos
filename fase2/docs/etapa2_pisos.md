# Etapa 2 — Pisos gratuitos, ablação por campo e entrada do enriquecimento

Pergunta desta etapa: o `enriquecimento_v01.jsonl` melhora a escolha do **ramo** o
suficiente para justificar o custo de produção, ou dá para chegar ao mesmo lugar só com
hierarquia e dicionário?

Tudo abaixo roda offline, em ~10 s, com `python -m src.pisos`. Nenhum número foi escolhido
por LLM: o artefato é insumo fixo e a métrica é `ramo@1`, pré-registrada para esta decisão.

## Métrica

`ramo@1` = o tema de nível 1 do top-1 é o ramo do tema central do gabarito. Medida nas
**92 questões com tema** (as 8 `fora` ficam de fora, como nas demais métricas de ramo).
É a métrica certa porque todas as 100 predições publicadas são de nível 1: a regra do pai
sempre promove, então o que importa é acertar o ramo, não o subtema.

`prec@20%` = precisão publicando os 20% de maior `rel` (fração de top-1 sobre top-2),
com a régua do case. Serve ao segundo critério de entrada (não cair na cobertura fixa).

## Pisos gratuitos

| variante do texto do tema | bm25 | rrf_all | rrf_tfidf_bm25 | tfidf | tfidf_char |
|---|---|---|---|---|---|
| base (caminho + título) | 0,500 | 0,630 | 0,587 | **0,641** | 0,554 |
| + filhos diretos | 0,533 | 0,630 | 0,598 | **0,641** | 0,598 |
| + dicionário | 0,489 | 0,620 | 0,587 | 0,630 | 0,565 |
| + filhos + dicionário | 0,511 | 0,641 | 0,576 | 0,630 | 0,609 |

**Os pisos gratuitos não saem do lugar.** O melhor piso continua em **0,641**
(`base`/`tfidf`, empatado com `filhos+dic`/`rrf_all`); nenhuma combinação de hierarquia e
dicionário chega a 0,691 (melhor piso + 0,05). Duas leituras:

- a hierarquia já está no texto do tema via `caminho`, então repetir os filhos só adiciona
  ruído — o ramo "fala" o vocabulário dos filhos por construção;
- o dicionário é um mapa questão→termo, não tema→termo; aplicado ao tema ele infla o texto
  com termos de leis que não distinguem ramos.

Isso responde a pergunta do passo 1: **não há como vencer o critério sem o artefato**.

## Ablação por campo (com o artefato completo)

| variante | bm25 | rrf_all | rrf_tfidf_bm25 | tfidf | tfidf_char |
|---|---|---|---|---|---|
| base | 0,500 | 0,630 | 0,587 | 0,641 | 0,554 |
| só sinônimos | 0,543 | 0,609 | 0,663 | 0,598 | 0,598 |
| só institutos | 0,587 | 0,674 | 0,641 | 0,641 | 0,685 |
| só texto | 0,630 | 0,674 | 0,630 | 0,565 | 0,652 |
| sinônimos + institutos | 0,641 | 0,696 | 0,663 | 0,630 | 0,696 |
| sinônimos + texto | 0,652 | 0,674 | 0,663 | 0,576 | 0,663 |
| institutos + texto | **0,707** | 0,696 | 0,674 | 0,609 | **0,739** |
| **completo** | 0,696 | **0,739** | 0,674 | 0,598 | 0,717 |

Três conclusões:

1. **Nenhum campo sozinho basta.** Sinônimos isolados ficam *abaixo* da base em `rrf_all`
   (0,609 vs 0,630): uma lista de paráfrases sem o vocabulário técnico do texto
   (institutos + definição) só acrescenta termos genéricos. Institutos são o campo mais
   forte isolado; texto é o que mais ajuda o `bm25`.
2. **O ganho vem da combinação.** Pares ficam entre 0,67 e 0,74; o conjunto completo é
   o melhor no `rrf_all` (0,739), e no `bm25` quem lidera é `instituições + texto` (0,707).
3. **O mínimo de sinônimos fica em 2.** A hipótese de voltar para 3 era "se sinônimos
   pesarem muito". A ablação mostra o contrário: sinônimos são o campo mais fraco sozinho.
   Forçar um terceiro termo só aumentaria o preenchimento sem mexer no `ramo@1`. O contrato
   permanece 2–5.

## Ablação leave-one-out: o campo faz falta?

A tabela anterior compara variantes; esta pergunta é outra: **tirar um campo do conjunto
completo piora?** Referência `enri` (sinônimos + institutos + texto), recuperador `rrf_all`,
n = 92, delta pareado com IC bootstrap:

| variante | ramo@1 | Δ vs completo | IC 95% | leitura |
|---|---|---|---|---|
| completo (`enri`) | **0,739** | — | — | referência |
| − sinônimos | 0,696 | −0,043 | −0,098..+0,011 | dentro do ruído |
| − institutos | 0,674 | −0,065 | −0,141..+0,011 | dentro do ruído (maior queda) |
| − texto | 0,696 | −0,043 | −0,098..0,000 | dentro do ruído |
| + dicionário | 0,685 | −0,054 | −0,109..−0,011 | **atrapalha** |
| + distinções | 0,750 | +0,011 | −0,044..+0,065 | dentro do ruído |

**Leitura.**

1. **Nenhum campo é individualmente necessário.** Todas as remoções ficam dentro do ruído —
   o que é coerente com o que a tabela anterior já mostrava: os campos isolados ficam abaixo
   da base e o ganho é da **combinação**. A conclusão vale só para as variantes testadas:
   leave-one-out não elimina interação entre campos (tirar sinônimos muda o que sobra).
2. **Institutos pesam mais** (−0,065), mas com 92 questões o IC não fecha.
3. **Somar o dicionário ao texto enriquecido atrapalha** (−0,054, IC exclui zero). O
   dicionário expande o texto base, que já está dentro do `enri`; a repetição dilui o sinal.
   Ele continua útil como piso grátis e na expansão de consulta, não como camada extra aqui.
4. **Distinções são neutras** (+0,011, IC inclui zero) e continuam fora do `texto_tema` —
   ficam como documentação do artefato, não como feature.

**Cuidado de seleção múltipla.** São 14 variantes × 5 recuperadores = **70 células**; o
máximo da grade é `dic+enri`/`tfidf_char` (0,761). Ele **não** é adotado: contra a
configuração entregue, o delta é +0,022 com IC [−0,044; +0,087] — indistinguível de zero —,
e trocar o recuperador é mudança de arquitetura. Escolher o máximo de 70 células com 92
questões é exatamente o erro que o protocolo evita.

## Critério de entrada

Melhor piso gratuito: **0,641** (`base` / `rrf_all`). Alvo: **≥ 0,691**.

| configuração | ramo@1 | delta vs base do mesmo recuperador (IC 95%) | prec@20% |
|---|---|---|---|
| **enri / rrf_all** | **0,739** | +0,109 (+0,033..+0,196) | 0,72 |
| enri / tfidf_char | 0,717 | +0,163 (+0,065..+0,261) | 0,94 |
| tudo / tfidf_char | 0,728 | +0,174 (+0,087..+0,272) | 0,83 |
| enri / bm25 | 0,696 | +0,196 (+0,098..+0,293) | 0,89 |

**Critério atendido.** A configuração adotada é `enri` com `rrf_all`, que é o recuperador
campeão já congelado na Fase 1 — nenhuma troca de arquitetura. O ganho de +0,109 é o maior
que a fusão entrega; o intervalo inferior fica acima de zero (+0,033), mas o ganho ainda é
modesto e o relatório deve dizer isso.

O `tfidf_char` ganha mais (+0,163, IC sem zero) porque o enriquecimento introduz variações
morfológicas que o n-grama de caractere captura melhor. Ele já é um dos três componentes do
`rrf_all`; trocá-lo pelo campeão custaria 0,022 de `ramo@1` (0,717 contra 0,739), dentro do
ruído — e não se troca arquitetura por empate.

Segundo critério: a precisão na cobertura fixa de 20% **não cai** — 0,72 no
`enri`/`rrf_all` (0,67 na leitura literal), contra 0,61 do melhor piso (`base`/`tfidf`) e
0,50 do `base`/`rrf_all`. O enriquecimento entra.

## O que isso autoriza

- o artefato passa a ser insumo do pipeline, lido de `enriquecimento_v01.jsonl`;
- `texto_tema` do pipeline passa a ser `caminho + título + sinônimos + institutos + texto`;
- os pisos gratuitos ficam registrados em `artefatos/pisos.csv` como controle negativo;
- a decisão vale para `ramo@1`; o efeito na precisão final é medido na Etapa 3, com a
  mesma regra seletiva e a mesma folha-verdade.

## Limitações

- n = 92 questões com tema; um acerto = 1,1 ponto percentual. O IC de Wilson do `ramo@1`
  do `enri`/`rrf_all` é [0,64; 0,82], largo.
- O ganho foi medido na folha-verdade, que também é a base de treino da confiança. O
  `ramo@1` não usa rótulo (é só top-1), mas a escolha da configuração viu as 100 questões;
  por isso o critério foi pré-registrado e é o único uso da métrica.
- `filhos+dic` no `tfidf_char` chega a 0,609 (acima do base do próprio char), mas ainda
  abaixo do melhor piso global. Não é vitória: é recuperar o atraso de um recuperador fraco.
