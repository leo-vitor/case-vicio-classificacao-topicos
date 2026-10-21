# Auditoria da camada de decisão — Fase 2

Seis itens, na ordem combinada (a régua primeiro, porque ela pode invalidar o resto).
Nada aqui muda a **arquitetura** (recuperação lexical, regra do pai, features): a
auditoria mexe só na **camada de decisão** e na **previsão**. Tudo reproduzível a partir
de `artefatos/*.json`.

> **Números atualizados após a Etapa 2 e a revisão de taxonomia (v02).** Toda esta
> auditoria foi reexecutada com o `texto_tema` enriquecido
> (`enriquecimento_v01.jsonl`, sha256 `7bbda02e4c65`) e com 5148/5156 reparentados sob
> 5155 (ver `docs/decisoes.md`, seção 12). O enriquecimento entrou por ter vencido o
> critério de `ramo@1` (0,739 contra piso 0,641); o efeito na estabilidade, em
> `docs/etapa5_cascata.md`.

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
| 1 | Métrica hierárquica | Literal 0,95 · estrita 0,50 · frouxa 0,90 | A meta **só existe na leitura literal**, que é a do LEIA-ME. Metade do acerto da regra final vem da promoção ao pai (estrita 0,50), mas o erro quase sempre fica no ramo certo (frouxa 0,90). |
| 2 | Validação aninhada | Vazamento confirmado: 33 → **15** publicadas ao corrigir; 13/15 = 0,867 | A cobertura a 95% era otimista em 18 publicações. A leitura honesta é 0,87 com IC [0,62; 0,96] — e é ela que limita a ambição do entregável. |
| 3 | Logística × manuais | Manuais com margem: **0 publicadas**; `branch_gap` 28/25; logística 33/30; bagging 32/29 | A logística ganha das manuais simples. Bagging empata dentro do ruído — não entra na regra, entra como medida de estabilidade. |
| 4 | O que se pode certificar | 95% e 90%: **impossível**. 12% de erro → 32/31; aninhado a 20% → 29/23 | A previsão deixa de ser artesanal: posterior Beta-Binomial + teto certificável (~79% no aninhado). |
| 5 | Conformidade (conjuntos + ancestral comum) | k̂ = 59 temas para 95% de cobertura → **0 publicações** | Descartado como regra; fica como diagnóstico: o ranqueamento continua plano demais para confinar num ramo. |
| 6 | Ponto de operação | 118 = 63 antigas + 55 novas; 6 publicações em Legislação Especial (antes 0); τ exato 0,88700901… | O τ arredondado não reproduzia o entregável; agora o valor exato e o consenso mínimo estão registrados. |

---

## 1. Métrica hierárquica: quanto do resultado depende da régua

A régua do LEIA-ME aceita **tema central, extra, pai direto ou filho direto**; irmão não
conta. Três leituras da *mesma* predição:

| Conjunto | Publicadas | Literal (régua do case) | Estrita (só exato/extra) | Frouxa (mesmo ramo nível 1) |
|---|---|---|---|---|
| Regra final (consenso ≥ 0,75 e τ = 0,8870) | 20 | **0,950** (19) | 0,500 (10) | 0,900 (18) |
| Consenso ≥ 0,75 (sem limiar) | 83 | 0,723 (60) | 0,458 (38) | 0,675 (56) |
| Publicando tudo | 100 | 0,680 (68) | 0,430 (43) | 0,610 (61) |

**Leitura.** A leitura literal é a do contrato, então é ela que vale — mas o número é
frágil à régua: na leitura estrita (publicar no tema exato) a regra final cai para 0,50,
ou seja, **metade do acerto vem da promoção ao pai**. A leitura frouxa (0,90) mostra que
o erro raramente sai do ramo: quando erra, erra o subtema dentro do ramo certo. O
enriquecimento melhorou as três leituras em relação ao baseline, mas não mudou esse
padrão — a hierarquia segue fazendo o trabalho pesado.

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
| Aninhado ingênuo (com vazamento) | 33 | 30 | 0,909 | 0,76–0,97 | 0,33 |
| **Aninhado corrigido** | 15 | 13 | **0,867** | 0,62–0,96 | 0,15 |

O limiar por fold no protocolo corrigido: 0,945 · 0,723 · 0,761 · 0,990 · 0,987 — uma
faixa larga. Isso diz duas coisas: (a) a cobertura a 95% era **otimista** (33 → 15);
(b) o τ **não é estável** entre folds, então reescolhê-lo por fold é ruído — a regra
entregue é fixa, escolhida nos 100, e a leitura que descreve o que foi entregue é a da
regra fixa (19/20), qualificada pelo aninhado corrigido (13/15) e pelo teto certificável
da seção 4.

## 3. Logística × regras manuais (mesmos folds, limiar no treino)

Todas com a mesma base (consenso = 1) e o limiar escolhido **fora** do grupo medido:

| Regra | Publicadas | Acertos | Precisão | Limite inferior (Wilson) | Cobertura |
|---|---|---|---|---|---|
| manual: consenso = 1 | 0 | 0 | — | — | 0,00 |
| manual: consenso = 1 ∧ `rel_pri` | 2 | 0 | 0,000 | 0,00 | 0,02 |
| manual: consenso = 1 ∧ `gap_pri` | 2 | 0 | 0,000 | 0,00 | 0,02 |
| manual: consenso = 1 ∧ `branch_gap` | 28 | 25 | 0,893 | 0,73 | 0,28 |
| logística (`p_oof`) | 33 | 30 | 0,909 | 0,76 | 0,33 |
| logística com bagging (200 reajustes) | 32 | 29 | 0,906 | 0,76 | 0,32 |

**Leitura.** As regras manuais simples **não sustentam 95% no treino em dobra nenhuma** —
por isso publicam 0. A margem sozinha não separa; ela só funciona combinada
(`branch_gap` publica 28 com 89% de acerto). A logística é a única que publica uma fração
útil com precisão perto da meta. O bagging empata (1 erro de diferença — dentro do ruído),
então **não entra na regra**: fica como instrumento, porque dá incerteza por questão
(desvio médio de 0,150 entre reajustes), útil para priorizar a fila de revisão humana.

Uma nota de honestidade: a essa altura as diferenças são menores que o ruído. Com 20–30
publicadas, 0,89 e 0,91 são o mesmo número.

## 4. O que 100 rótulos provam (controle de risco e precisão certificável)

Dois instrumentos, medidos no OOF, todos com a cota exata de **Clopper-Pearson**.

**Controle de risco conformal (perda conjunta).** Garante `E[publicar e errar] ≤ α` — isto
é, limita o *total* de publicações erradas na amostra, o que é mais fraco que a precisão
condicional:

| α | Limiar | Publicadas | Acertos | Precisão | Cobertura |
|---|---|---|---|---|---|
| 0,05 | 0,488 | 41 | 37 | 0,902 | 0,41 |
| 0,10 | 0,211 | 48 | 39 | 0,813 | 0,48 |
| ≥0,15 | 0,032 | 51 | 41 | 0,804 | 0,51 |

**Precisão certificável** (cota superior do erro entre as publicadas ≤ α) — o instrumento
honesto para a pergunta "95% se sustenta?":

| α (erro) | In-sample: publicadas / acertos | Cota superior do erro | Aninhado corrigido: publicadas / acertos |
|---|---|---|---|
| 0,05 | **0** | — | **0** |
| 0,10 | **0** | — | **0** |
| 0,12 | 32 / 31 | 0,110 | — |
| 0,15 | 33 / 31 | 0,137 | 7 / 6 |
| 0,20 | 44 / 38 | 0,199 | 29 / 23 |
| 0,25 | 51 / 41 | 0,248 | 48 / 38 |

**Leitura.** Com 100 rótulos **não se certifica 95% nem 90%** em cobertura alguma: para 0
erros, 95% exigiria 60 publicadas perfeitas, e o modelo não chega perto disso. O primeiro
nível certificável é 12% de erro (32 publicadas, 31 acertos). No protocolo aninhado — o
que vale — a certificação honesta fica em **0,79 de precisão** com 29 publicadas. Isto
não é um defeito do método: é o que 100 rótulos permitem afirmar. Aumentar a cobertura ou
provar 95% exige rotular mais questões.

**Conjuntos conformais + regra do ancestral comum** (pedido explicitamente). O conjunto é
`{k̂ melhores temas}`, com `k̂` calibrado para o gabarito estar dentro em 1−α dos casos; a
regra publica o tema de nível 1 quando o conjunto inteiro cai num único ramo:

| α | k̂ (de 371 temas) | Cobertura do conjunto | Publicadas pela regra |
|---|---|---|---|
| 0,05 | 59 | 0,967 | **0** |
| 0,10 | 22 | 0,913 | **0** |
| 0,20 | 8 | 0,815 | 1 (1 acerto) |

É válido e é quase inútil: com o ranqueamento atual, o conjunto necessário para 95% de
cobertura tem 59 temas, que nunca cabem num ramo. Como diagnóstico, é preciso — **o
gargalo é o ranqueamento, não o limiar**. A mesma ideia sem garantia, variando k, mostra
onde estaria o ganho se o ranking melhorasse:

| top-k confinado num ramo | k=1 | k=2 | k=3 | k=4 | k=5 | k=6 | k=7 |
|---|---|---|---|---|---|---|---|
| publicadas | 100 | 39 | 28 | 15 | 8 | 4 | 3 |
| precisão | 0,680 | 0,872 | 0,929 | 0,933 | 1,000 | 1,000 | 1,000 |

(k=1 é a própria regra do pai, 0,68 — a curva começa exatamente onde o baseline está.)

## 5. Ponto de operação: origem das 118 publicações

| Faixa | Publicadas | Revisar | Cobertura |
|---|---|---|---|
| antigas (Q0001–Q0359, 359) | 63 | 296 | 0,176 |
| novas (Q0360–Q0659, 300) | 55 | 245 | 0,183 |
| **total** | **118** | **541** | **0,179** |

Por ramo: Penal 65, Processo Penal 41, Legislação Especial 6, Criminologia 6. A entrada de
Legislação Especial (antes **nenhuma**) e de Criminologia é efeito direto do enriquecimento:
os temas desses estratos passaram a ter o vocabulário que os enunciados usam. Penal e
Processo Penal continuam concentrando a cobertura porque concentram os rótulos (40 e 30 dos
100), não porque a regra os prefira.

**Regra exata entregue:** `consenso_top1 ≥ 0,75` **e** `p ≥ 0,8870090102078212`.

**Incompatibilidade de escala (item 5 do pedido).** O τ vem de `p_oof` (modelos treinados
em 80) e é aplicado a `p_all` (modelo treinado nos 100). As médias:

| Grandeza | Média |
|---|---|
| `p_oof` nas 100 | 0,570 |
| `p_all` nas 659 | 0,571 |
| `p_all` nas antigas (259 fora da folha) | 0,549 |
| `p_all` nas novas (300) | 0,598 |

No agregado as escalas coincidem (0,570 contra 0,571), mas **não** por faixa: nas novas o
modelo fica 0,05 mais confiante — e a cobertura vai a 0,18 contra 0,18. É a mesma
assimetria residual de antes do enriquecimento, só que menor: o ganho não veio de
"empurrar" as novas para publicar, veio de vocabulário.

## 6. Congelamento e proveniência

`artefatos/auditoria.json` traz o manifesto: commit, versão de Python, versões de
`numpy`/`pandas`/`sklearn`/`scipy`, semente, repetições/folds, o hash do
`enriquecimento_v01.jsonl` e os hashes (sha256 truncado em 16) de `publicacao.csv`,
`previsao.txt`, `temas.csv`, `folha_verdade.csv`, `questoes.jsonl` e
`dicionario_juridico.csv`.

| Arquivo | sha256 (16) |
|---|---|
| `enriquecimento_v01.jsonl` | `7bbda02e4c658484` |
| `publicacao.csv` | `bda0d76ddab576cf` |
| `previsao.txt` | `22f995f559e95591` |

O hash de `publicacao.csv` muda a cada reexecução legítima do pipeline (é o entregável), por
isso o manifesto grava o valor da execução que gerou o `previsao.txt` ao lado. Os demais
insumos (`temas.csv`, `folha_verdade.csv`, `questoes.jsonl`, `dicionario_juridico.csv`)
permanecem idênticos aos da Fase 1. A árvore efetiva é `temas.csv` + os ajustes de
`src/taxonomia.py` (v02); o hash acima é o do CSV cru, como veio do case. O
`enriquecimento_v01.jsonl` é o único insumo novo.
