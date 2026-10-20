# Auditoria da camada de decisão — Fase 2

Seis itens, na ordem combinada (a régua primeiro, porque ela pode invalidar o resto).
Nada aqui muda a **arquitetura** (recuperação lexical, regra do pai, features): a
auditoria mexe só na **camada de decisão** e na **previsão**. Tudo reproduzível a partir
de `artefatos/*.json`.

Comandos:

```bash
cd fase2
.venv/bin/python -m src.clean       # anexos -> texto limpo
.venv/bin/python -m src.decisao     # regra seletiva -> publicacao.csv
.venv/bin/python -m src.conformal   # CRC, precisão certificável, conjuntos conformais
.venv/bin/python -m src.auditoria   # comparação de regras, aninhado corrigido, manifesto
.venv/bin/python -m src.previsao    # previsao.txt (usa os resumos acima)
```

## Veredito, em uma tabela

| # | Item | Resultado | Consequência |
|---|---|---|---|
| 1 | Métrica hierárquica | Literal 0,95 · estrita 0,45 · frouxa 0,75 | A meta **só existe na leitura literal**, que é a do LEIA-ME. Quanto do resultado depende da régua fica explícito. |
| 2 | Validação aninhada | Tinha vazamento: 15 → **10** publicadas ao corrigir | A cobertura a 95% era otimista. A leitura honesta é 9/10 = 0,90. |
| 3 | Logística × manuais | Manuais com margem: **0 publicadas**; `branch_gap` 6/6; logística 13/15; bagging 13/14 | A logística ganha das manuais simples. Bagging empata dentro do ruído — não entra na regra, entra como medida de estabilidade. |
| 4 | O que se pode certificar | 95% e 90%: **impossível**. 15% de erro → 22/21; aninhado a 20% → 16/20 | A previsão deixa de ser artesanal: posterior Beta-Binomial + teto certificável (~80%). |
| 5 | Conformidade (conjuntos + ancestral comum) | k̂ = 90 temas para 95% de cobertura → **0 publicações** | Descartado como regra; fica como diagnóstico: o ranqueamento é plano demais para confinar num ramo. |
| 6 | Ponto de operação | 131 = 55 antigas + 76 novas, 100% em Penal/Processo Penal; τ exato 0,87146344… | O τ arredondado (0,8715) não reproduzia o entregável; agora o valor exato está registrado. |

---

## 1. Métrica hierárquica: quanto do resultado depende da régua

A régua do LEIA-ME aceita **tema central, extra, pai direto ou filho direto**; irmão não
conta. Três leituras da *mesma* predição:

| Conjunto | Publicadas | Literal (régua do case) | Estrita (só exato/extra) | Frouxa (mesmo ramo nível 1) |
|---|---|---|---|---|
| Regra final (consenso=1 e τ=0,87146) | 20 | **0,950** (19) | 0,450 (9) | 0,750 (15) |
| Consenso = 1 (sem limiar) | 48 | 0,792 (38) | 0,500 (24) | 0,708 (34) |
| Publicando tudo | 100 | 0,590 (59) | 0,340 (34) | 0,490 (49) |

**Leitura.** A leitura literal é a do contrato, então é ela que vale — mas o número é
frágil à régua: na leitura estrita (publicar no tema exato) a regra final cai para 0,45,
ou seja, **mais da metade do acerto vem da promoção ao pai**. Isso também explica por que a
"regra do pai" é dominante (ganha +3/+4 e nunca perde): ela é ótima *para esta régua*.
Consequência prática: se o avaliador aplicar leitura estrita, o resultado não se sustenta,
e nenhuma quantidade de ajuste na camada de decisão resolve — teria de mudar o
recuperador (acertar o subtema exato).

`extras_ids` **não** é multilabel: conta-se como acerto publicar em qualquer um dos alvos,
não é preciso listar todos. A leitura frouxa (mesmo ramo) não é do case e serve só para
mostrar onde o erro está: a maior parte do erro literal mora **dentro do ramo certo**
(0,75 frouxa contra 0,45 estrita).

## 2. Validação aninhada: havia vazamento

O protocolo escolhia o limiar no treino usando `p_oof` global, cujas dobras internas
podiam ter sido treinadas **vendo o grupo de teste externo**. Correção (`p_interno` em
`src/auditoria.py`): para o fold externo *k*, o limiar é escolhido com probabilidades de
modelos treinados em 3/4 do treino (nunca viram o fold de teste nem a própria questão), e
aplicado ao teste com um modelo treinado só no treino.

| Protocolo | Publicadas | Acertos | Precisão | IC 95% | Cobertura |
|---|---|---|---|---|---|
| Aninhado ingênuo (com vazamento) | 15 | 13 | 0,867 | 0,62–0,96 | 0,15 |
| **Aninhado corrigido** | 10 | 9 | **0,900** | 0,60–0,98 | 0,10 |

O limiar por fold no protocolo corrigido: 0,797 · 0,913 · 0,892 · 0,862 · 0,982 — uma
faixa larga. Isso diz duas coisas: (a) a cobertura a 95% era **otimista** (15 → 10);
(b) o τ **não é estável** entre folds, então reescolhê-lo por fold é ruído — a regra
entregue é fixa, escolhida nos 100, e a leitura que descreve o que foi entregue é a da
regra fixa (19/20), qualificada pelo aninhado corrigido (9/10) e pelo teto certificável
da seção 4.

## 3. Logística × regras manuais (mesmos folds, limiar no treino)

Todas com a mesma base (consenso = 1) e o limiar escolhido **fora** do grupo medido:

| Regra | Publicadas | Acertos | Precisão | Limite inferior (Wilson) | Cobertura |
|---|---|---|---|---|---|
| manual: consenso = 1 | 0 | 0 | — | — | 0,00 |
| manual: consenso = 1 ∧ `rel_pri` | 0 | 0 | — | — | 0,00 |
| manual: consenso = 1 ∧ `gap_pri` | 0 | 0 | — | — | 0,00 |
| manual: consenso = 1 ∧ `branch_gap` | 6 | 6 | 1,000 | 0,61 | 0,06 |
| logística (`p_oof`) | 15 | 13 | 0,867 | 0,62 | 0,15 |
| logística com bagging (200 reajustes) | 14 | 13 | 0,929 | 0,69 | 0,14 |

**Leitura.** As regras manuais simples **não sustentam 95% no treino em dobra nenhuma** —
por isso publicam 0. A margem sozinha não separa; ela só funciona combinada
(`branch_gap` publica 6 com 100% de acerto, mas a cobertura de 6% é inútil na prática).
A logística não é um ganho retumbante, mas é a única que publica uma fração útil com
precisão perto da meta. O bagging empata (1 erro em 14 contra 2 em 15 — dentro do ruído),
então **não entra na regra**: fica como instrumento, porque dá incerteza por questão
(desvio médio de 0,15 entre reajustes), útil para priorizar a fila de revisão humana.

Uma nota de honestidade: a essa altura as diferenças são menores que o ruído. Com 10–20
publicadas, 0,87 e 0,93 são o mesmo número.

## 4. O que 100 rótulos provam (controle de risco e precisão certificável)

Dois instrumentos, medidos no OOF, todos com a cota exata de **Clopper-Pearson**.

**Controle de risco conformal (perda conjunta).** Garante `E[publicar e errar] ≤ α` — isto
é, limita o *total* de publicações erradas na amostra, o que é mais fraco que a precisão
condicional:

| α | Limiar | Publicadas | Acertos | Precisão | Cobertura |
|---|---|---|---|---|---|
| 0,05 | 0,759 | 32 | 28 | 0,875 | 0,32 |
| 0,10 | 0,339 | 44 | 35 | 0,795 | 0,44 |
| ≥0,15 | 0,003 | 48 | 38 | 0,792 | 0,48 |

**Precisão certificável** (cota superior do erro entre as publicadas ≤ α) — o instrumento
honesto para a pergunta "95% se sustenta?":

| α (erro) | In-sample: publicadas / acertos | Cota superior do erro | Aninhado corrigido: publicadas / acertos |
|---|---|---|---|
| 0,05 | **0** | — | **0** |
| 0,10 | **0** | — | **0** |
| 0,15 | 22 / 21 | 0,145 | 4 / 3 |
| 0,20 | 29 / 26 | 0,182 | 20 / 16 |
| 0,25 | 43 / 35 | 0,243 | 28 / 23 |

**Leitura.** Com 100 rótulos **não se certifica 95% nem 90%** em cobertura alguma: para 0
erros, 95% exigiria 60 publicadas perfeitas, e o modelo não chega perto disso. O primeiro
nível certificável é 15% de erro (22 publicadas, 21 acertos). No protocolo aninhado — o
que vale — a certificação honesta fica em **~80% de precisão**. Isto não é um defeito do
método: é o que 100 rótulos permitem afirmar. Aumentar a cobertura ou provar 95% exige
rotular mais questões.

**Conjuntos conformais + regra do ancestral comum** (pedido explicitamente). O conjunto é
`{k̂ melhores temas}`, com `k̂` calibrado para o gabarito estar dentro em 1−α dos casos; a
regra publica o tema de nível 1 quando o conjunto inteiro cai num único ramo:

| α | k̂ (de 371 temas) | Cobertura do conjunto | Publicadas pela regra |
|---|---|---|---|
| 0,05 | 90 | 0,967 | **0** |
| 0,10 | 42 | 0,913 | **0** |
| 0,20 | 16 | 0,815 | **0** |

É válido e é inútil: com o ranqueamento lexical atual, o conjunto necessário para 95% de
cobertura tem 90 temas, que nunca cabem num ramo. Como diagnóstico, é preciso — **o
gargalo é o ranqueamento, não o limiar**. A mesma ideia sem garantia, variando k, mostra
onde estaria o ganho se o ranking melhorasse:

| top-k confinado num ramo | k=1 | k=2 | k=3 | k=4 | k=5 | k≥6 |
|---|---|---|---|---|---|---|
| publicadas | 100 | 45 | 30 | 17 | 9 | ~0 |
| precisão | 0,590 | 0,778 | 0,733 | 0,824 | 0,889 | — |

(k=1 é a própria regra do pai, 0,59 — a curva começa exatamente onde o baseline está.)

## 5. Ponto de operação: origem das 131 publicações

| Faixa | Publicadas | Revisar | Cobertura |
|---|---|---|---|
| antigas (Q0001–Q0359, 359) | 55 | 304 | 0,153 |
| novas (Q0360–Q0659, 300) | 76 | 224 | 0,253 |
| **total** | **131** | **528** | 0,199 |

Por ramo: Penal 79, Processo Penal 52 — **nenhuma** em Legislação Especial ou
Criminologia. Não é acaso: esses dois estratos têm 12 e 10 exemplos rotulados, e o
consenso = 1 (os 4 recuperadores concordando no mesmo nó) é raro neles; a regra
simplesmente não publica onde não tem evidência. Fica registrado como limitação de
cobertura, não como erro.

**Regra exata entregue:** `consenso_top1 = 1,00` **e** `p ≥ 0,8714634364257998`
(o `decisao_resumo.json` passou a guardar o valor exato; antes só o arredondado 0,8715,
que publicava 19 em vez de 20 e não reproduzia o `publicacao.csv`).

**Incompatibilidade de escala (item 5 do pedido).** O τ vem de `p_oof` (modelos treinados
em 80) e é aplicado a `p_all` (modelo treinado nos 100). As médias:

| Grandeza | Média |
|---|---|
| `p_oof` nas 100 | 0,534 |
| `p_all` nas 659 | 0,535 |
| `p_all` nas antigas (259 fora da folha) | 0,491 |
| `p_all` nas novas (300) | 0,588 |

No agregado as escalas coincidem (0,534 contra 0,535), mas **não** por faixa: nas novas o
modelo fica 0,10 mais confiante. É por isso que a cobertura sobe nas novas (0,25 contra
0,14). Não há como decidir se é facilidade ou excesso fora da distribuição sem rótulo —
mas é uma hipótese verificável, não um detalhe: se a mudança de 360 questões deslocou a
distribuição, a precisão nas novas é **menor** que nas antigas.

## 6. Congelamento e proveniência

`artefatos/auditoria.json` traz o manifesto: commit, versão de Python, versões de
`numpy`/`pandas`/`sklearn`/`scipy`, semente, repetições/folds e os hashes (sha256 truncado
em 16) de `publicacao.csv`, `previsao.txt`, `temas.csv`, `folha_verdade.csv`,
`questoes.jsonl` e `dicionario_juridico.csv`.

| Arquivo | sha256 (16) |
|---|---|
| `publicacao.csv` | `b050cefdb8dfb1cb` |
| `previsao.txt` | `4417be585075bf3a` |
| `temas.csv` | `9c6e98a6cd568816` |
| `folha_verdade.csv` | `c1412ce8d336ae24` |
| `dicionario_juridico.csv` | `4de77271944d32c4` |

`publicacao.csv` **não mudou** nesta auditoria (mesmo hash): a regra foi congelada, o que
mudou foi o que se afirma sobre ela.

## O que muda na entrega

| Item | Antes | Depois |
|---|---|---|
| Regra | consenso=1 ∧ p ≥ 0,8715 (arredondado) | consenso=1 ∧ p ≥ 0,8714634364257998 (exato, registrado) |
| `publicacao.csv` | 131 publicar / 528 revisar | **igual** (mesmo hash) |
| `previsao.txt` | 0,92 [0,82–0,97], fórmula artesanal | **0,91 [0,76–0,99]**, posterior Beta-Binomial + teto certificável |
| Leituras | in-sample e aninhada | + aninhada **corrigida** (sem vazamento) e certificável |
| Módulos | — | `src/conformal.py`, `src/auditoria.py`, `src/artefato.py` |

A previsão ficou **mais baixa e mais larga** (0,91 contra 0,92; 0,76–0,99 contra
0,82–0,97) porque o número passou a sair da distribuição e não de um desconto escolhido à
mão. Nada no entregável (`publicacao.csv`) mudou — a revisão é de honestidade, não de
operação.

## Limites desta auditoria

1. **100 rótulos.** Toda comparação entre regras vive dentro do ruído: os intervalos de
   Wilson de 10–20 publicadas cobrem quase tudo. O resultado não é "a logística é melhor";
   é "as manuais simples não sustentam 95% no treino".
2. **A conformidade assume mesma distribuição** entre as 100 e as 559. É hipótese, não
   fato — e o deslocamento de confiança nas novas (0,49 → 0,59) sugere que ela pode
   falhar.
3. **Tudo depende da régua** (seção 1). Na leitura estrita, a precisão cai para 0,45.
4. **As 8 questões `fora` da taxonomia** continuam sem sinal discriminante; `revisar` é
   conservador e não afeta a precisão das publicadas.
