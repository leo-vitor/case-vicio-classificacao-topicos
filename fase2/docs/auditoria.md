# Auditoria da camada de decisão — Fase 2

Seis itens, na ordem combinada (a régua primeiro, porque ela pode invalidar o resto).
Nada aqui muda a **arquitetura** (recuperação lexical, regra do pai, features): a
auditoria mexe só na **camada de decisão** e na **previsão**. Tudo reproduzível a partir
de `artefatos/*.json`.

> **Números atualizados após a Etapa 2.** Toda esta auditoria foi reexecutada com o
> `texto_tema` enriquecido (`enriquecimento_v01.jsonl`, sha256 `d906aa5a5619`), que entrou
> por ter vencido o critério de `ramo@1` (0,728 contra piso 0,641). A decisão e o porquê
> estão em `docs/etapa2_pisos.md`; o efeito na estabilidade, em `docs/etapa5_cascata.md`.

Comandos:

```bash
cd fase2
.venv/bin/python -m src.clean       # anexos -> texto limpo
.venv/bin/python -m src.decisao     # regra seletiva -> publicacao.csv
.venv/bin/python -m src.conformal   # CRC, precisão certificável, conjuntos conformais
.venv/bin/python -m src.auditoria   # comparação de regras, aninhado corrigido, manifesto
.venv/bin/python -m src.previsao    # previsao.txt (usa os resumos acima)
.venv/bin/python -m src.pisos       # pisos gratuitos + ablação por campo
.venv/bin/python -m src.cascata     # ramo em 2 estágios + disciplina como prior
```

## Veredito, em uma tabela

| # | Item | Resultado | Consequência |
|---|---|---|---|
| 1 | Métrica hierárquica | Literal 0,95 · estrita 0,55 · frouxa 0,90 | A meta **só existe na leitura literal**, que é a do LEIA-ME. O enriquecimento subiu a leitura estrita de 0,45 para 0,55: parte do ganho é real, parte continua sendo promoção ao pai. |
| 2 | Validação aninhada | Vazamento confirmado: 32 → **20** publicadas ao corrigir; 18/20 = 0,900 | A cobertura a 95% era otimista em 12 publicações. A leitura honesta é 0,90 com IC [0,70; 0,97]. |
| 3 | Logística × manuais | Manuais com margem: **0 publicadas**; `branch_gap` 28/25; logística 32/29; bagging 31/28 | A logística ganha das manuais simples. Bagging empata dentro do ruído — não entra na regra, entra como medida de estabilidade. |
| 4 | O que se pode certificar | 95% e 90%: **impossível**. 15% de erro → 33/31; aninhado a 20% → 41/35 | A previsão deixa de ser artesanal: posterior Beta-Binomial + teto certificável (~85–90% com o ranqueamento novo). |
| 5 | Conformidade (conjuntos + ancestral comum) | k̂ = 60 temas para 95% de cobertura → **0 publicações** | Descartado como regra; fica como diagnóstico: o ranqueamento continua plano demais para confinar num ramo. |
| 6 | Ponto de operação | 130 = 70 antigas + 60 novas; 4 publicações em Legislação Especial (antes 0); τ exato 0,89617326… | O τ arredondado não reproduzia o entregável; agora o valor exato e o consenso mínimo estão registrados. |

---

## 1. Métrica hierárquica: quanto do resultado depende da régua

A régua do LEIA-ME aceita **tema central, extra, pai direto ou filho direto**; irmão não
conta. Três leituras da *mesma* predição:

| Conjunto | Publicadas | Literal (régua do case) | Estrita (só exato/extra) | Frouxa (mesmo ramo nível 1) |
|---|---|---|---|---|
| Regra final (consenso ≥ 0,75 e τ = 0,89617) | 20 | **0,950** (19) | 0,550 (11) | 0,900 (18) |
| Consenso ≥ 0,75 (sem limiar) | 82 | 0,732 (60) | 0,463 (38) | 0,683 (56) |
| Publicando tudo | 100 | 0,670 (67) | 0,420 (42) | 0,600 (60) |

**Leitura.** A leitura literal é a do contrato, então é ela que vale — mas o número é
frágil à régua: na leitura estrita (publicar no tema exato) a regra final cai para 0,55,
ou seja, **quase metade do acerto ainda vem da promoção ao pai**. O enriquecimento melhorou
as três leituras (0,59 → 0,67 literal; 0,34 → 0,42 estrita; 0,49 → 0,60 frouxa no
"publicando tudo"), o que mostra que o ganho não é só de ramo: o subtema também ficou mais
perto. Ainda assim, a hierarquia segue fazendo o trabalho pesado.

`extras_ids` **não** é multilabel: conta-se como acerto publicar em qualquer um dos alvos,
não é preciso listar todos. A leitura frouxa (mesmo ramo) não é do case e serve só para
mostrar onde o erro está.

## 2. Validação aninhada: havia vazamento

O protocolo escolhia o limiar no treino usando `p_oof` global, cujas dobras internas
podiam ter sido treinadas **vendo o grupo de teste externo**. Correção (`p_interno` em
`src/auditoria.py`): para o fold externo *k*, o limiar é escolhido com probabilidades de
modelos treinados em 3/4 do treino (nunca viram o fold de teste nem a própria questão), e
aplicado ao teste com um modelo treinado só no treino.

| Protocolo | Publicadas | Acertos | Precisão | IC 95% | Cobertura |
|---|---|---|---|---|---|
| Aninhado ingênuo (com vazamento) | 32 | 29 | 0,906 | 0,76–0,97 | 0,32 |
| **Aninhado corrigido** | 20 | 18 | **0,900** | 0,70–0,97 | 0,20 |

O limiar por fold no protocolo corrigido: 0,869 · 0,704 · 0,783 · 0,988 · 0,811 — uma
faixa larga. Isso diz duas coisas: (a) a cobertura a 95% era **otimista** (32 → 20);
(b) o τ **não é estável** entre folds, então reescolhê-lo por fold é ruído — a regra
entregue é fixa, escolhida nos 100, e a leitura que descreve o que foi entregue é a da
regra fixa (19/20), qualificada pelo aninhado corrigido (18/20) e pelo teto certificável
da seção 4.

## 3. Logística × regras manuais (mesmos folds, limiar no treino)

Todas com a mesma base (consenso = 1) e o limiar escolhido **fora** do grupo medido:

| Regra | Publicadas | Acertos | Precisão | Limite inferior (Wilson) | Cobertura |
|---|---|---|---|---|---|
| manual: consenso = 1 | 0 | 0 | — | — | 0,00 |
| manual: consenso = 1 ∧ `rel_pri` | 2 | 0 | 0,000 | 0,00 | 0,02 |
| manual: consenso = 1 ∧ `gap_pri` | 2 | 0 | 0,000 | 0,00 | 0,02 |
| manual: consenso = 1 ∧ `branch_gap` | 28 | 25 | 0,893 | 0,73 | 0,28 |
| logística (`p_oof`) | 32 | 29 | 0,906 | 0,76 | 0,32 |
| logística com bagging (200 reajustes) | 31 | 28 | 0,903 | 0,75 | 0,31 |

**Leitura.** As regras manuais simples **não sustentam 95% no treino em dobra nenhuma** —
por isso publicam 0. A margem sozinha não separa; ela só funciona combinada
(`branch_gap` publica 28 com 89% de acerto). A logística é a única que publica uma fração
útil com precisão perto da meta. O bagging empata (1 erro de diferença — dentro do ruído),
então **não entra na regra**: fica como instrumento, porque dá incerteza por questão
(desvio médio de 0,145 entre reajustes), útil para priorizar a fila de revisão humana.

Uma nota de honestidade: a essa altura as diferenças são menores que o ruído. Com 20–30
publicadas, 0,89 e 0,93 são o mesmo número.

## 4. O que 100 rótulos provam (controle de risco e precisão certificável)

Dois instrumentos, medidos no OOF, todos com a cota exata de **Clopper-Pearson**.

**Controle de risco conformal (perda conjunta).** Garante `E[publicar e errar] ≤ α` — isto
é, limita o *total* de publicações erradas na amostra, o que é mais fraco que a precisão
condicional:

| α | Limiar | Publicadas | Acertos | Precisão | Cobertura |
|---|---|---|---|---|---|
| 0,05 | 0,536 | 40 | 36 | 0,900 | 0,40 |
| 0,10 | 0,173 | 49 | 40 | 0,816 | 0,49 |
| ≥0,15 | 0,003 | 51 | 41 | 0,804 | 0,51 |

**Precisão certificável** (cota superior do erro entre as publicadas ≤ α) — o instrumento
honesto para a pergunta "95% se sustenta?":

| α (erro) | In-sample: publicadas / acertos | Cota superior do erro | Aninhado corrigido: publicadas / acertos |
|---|---|---|---|
| 0,05 | **0** | — | **0** |
| 0,10 | **0** | — | **0** |
| 0,15 | 33 / 31 | 0,137 | 10 / 8 |
| 0,20 | 45 / 39 | 0,195 | 41 / 35 |
| 0,25 | 51 / 41 | 0,248 | 48 / 38 |

**Leitura.** Com 100 rótulos **não se certifica 95% nem 90%** em cobertura alguma: para 0
erros, 95% exigiria 60 publicadas perfeitas, e o modelo não chega perto disso. O primeiro
nível certificável é 15% de erro (33 publicadas, 31 acertos). No protocolo aninhado — o
que vale — a certificação honesta fica em **~85% de precisão** com 41 publicadas. Isto não
é um defeito do método: é o que 100 rótulos permitem afirmar. Aumentar a cobertura ou
provar 95% exige rotular mais questões.

**Conjuntos conformais + regra do ancestral comum** (pedido explicitamente). O conjunto é
`{k̂ melhores temas}`, com `k̂` calibrado para o gabarito estar dentro em 1−α dos casos; a
regra publica o tema de nível 1 quando o conjunto inteiro cai num único ramo:

| α | k̂ (de 371 temas) | Cobertura do conjunto | Publicadas pela regra |
|---|---|---|---|
| 0,05 | 60 | 0,967 | **0** |
| 0,10 | 22 | 0,913 | **0** |
| 0,20 | 8 | 0,815 | 1 (1 acerto) |

É válido e é quase inútil: com o ranqueamento atual, o conjunto necessário para 95% de
cobertura tem 60 temas, que nunca cabem num ramo. Como diagnóstico, é preciso — **o
gargalo é o ranqueamento, não o limiar**. A mesma ideia sem garantia, variando k, mostra
onde estaria o ganho se o ranking melhorasse:

| top-k confinado num ramo | k=1 | k=2 | k=3 | k=4 | k=5 | k≥6 |
|---|---|---|---|---|---|---|
| publicadas | 100 | 39 | 28 | 14 | 7 | 4 |
| precisão | 0,670 | 0,872 | 0,929 | 0,929 | 1,000 | 1,000 |

(k=1 é a própria regra do pai, 0,67 — a curva começa exatamente onde o baseline está.)

## 5. Ponto de operação: origem das 130 publicações

| Faixa | Publicadas | Revisar | Cobertura |
|---|---|---|---|
| antigas (Q0001–Q0359, 359) | 70 | 289 | 0,195 |
| novas (Q0360–Q0659, 300) | 60 | 240 | 0,200 |
| **total** | **130** | **529** | 0,197 |

Por ramo: Penal 69, Processo Penal 44, Criminologia 13, Legislação Especial 4. A entrada de
Legislação Especial (antes **nenhuma**) e de Criminologia é efeito direto do enriquecimento:
os temas desses estratos passaram a ter o vocabulário que os enunciados usam. Penal e
Processo Penal continuam concentrando a cobertura porque concentram os rótulos (40 e 30 dos
100), não porque a regra os prefira.

**Regra exata entregue:** `consenso_top1 ≥ 0,75` **e** `p ≥ 0,8961732685791203`.

**Incompatibilidade de escala (item 5 do pedido).** O τ vem de `p_oof` (modelos treinados
em 80) e é aplicado a `p_all` (modelo treinado nos 100). As médias:

| Grandeza | Média |
|---|---|
| `p_oof` nas 100 | 0,570 |
| `p_all` nas 659 | 0,566 |
| `p_all` nas antigas (259 fora da folha) | 0,543 |
| `p_all` nas novas (300) | 0,594 |

No agregado as escalas coincidem (0,570 contra 0,566), mas **não** por faixa: nas novas o
modelo fica 0,05 mais confiante. Antes do enriquecimento a diferença era 0,10 e a cobertura
ia de 0,14 (antigas) para 0,25 (novas); agora é 0,19 contra 0,20. O enriquecimento
**reduziu** a assimetria entre faixas — o indício mais forte de que ele não é um ajuste
local.

## 6. Congelamento e proveniência

`artefatos/auditoria.json` traz o manifesto: commit, versão de Python, versões de
`numpy`/`pandas`/`sklearn`/`scipy`, semente, repetições/folds, o hash do
`enriquecimento_v01.jsonl` e os hashes (sha256 truncado em 16) de `publicacao.csv`,
`previsao.txt`, `temas.csv`, `folha_verdade.csv`, `questoes.jsonl` e
`dicionario_juridico.csv`.

| Arquivo | sha256 (16) |
|---|---|
| `enriquecimento_v01.jsonl` | `d906aa5a5619e450` |
| `publicacao.csv` | `ed240561590c5786` |
| `previsao.txt` | `98296b0104a8aa00` |

O hash de `publicacao.csv` muda a cada reexecução legítima do pipeline (é o entregável), por
isso o manifesto grava o valor da execução que gerou o `previsao.txt` ao lado. Os demais
insumos (`temas.csv`, `folha_verdade.csv`, `questoes.jsonl`, `dicionario_juridico.csv`)
permanecem idênticos aos da Fase 1, e o `enriquecimento_v01.jsonl` é o único insumo novo.
