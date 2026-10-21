# Etapa 5 — Ramo em dois estágios, disciplina como prior e estabilidade

Duas perguntas:

1. Vale decidir o ramo em um estágio próprio (agregando os filhos, com a disciplina de
   origem como prior) em vez de simplesmente promover o top-1 plano?
2. A adoção do enriquecimento deixa a saída estável, ou só troca um conjunto de erros por
   outro?

Tudo com o texto enriquecido (`enri`), 92 questões com tema, `python -m src.cascata`.

## Estágio 1 — agregação por ramo

| agregação | ramo@1 | IC 95% | Δ pareado vs `max` | IC do Δ |
|---|---|---|---|---|
| `max` (ramo do top-1 plano) | 0,739 | 0,641–0,818 | — | — |
| `soma3` (3 melhores do ramo) | 0,652 | 0,551–0,742 | −0,087 | −0,185..+0,011 |
| `media` (média do ramo) | 0,457 | 0,359–0,558 | −0,271 | −0,380..−0,163 |

`max` **é** o ramo do top-1 plano: o máximo da agregação sobre os ramos coincide com o
ramo da coluna de maior score. Ou seja, a "cascata" com agregação por máximo não é um
modelo novo — é a mesma decisão com outro nome. `soma3` e `media` pioram porque premeiam
ramo grande e diluem ramo com um único descendente forte.

## Estágio 1 — disciplina como prior

A disciplina de origem (`disciplina_origem`, metadado da questão) acerta a raiz do tema
central em **73/92 = 0,793**. Como filtro rígido, perderia 19 questões — rejeitado.

Como prior aditivo no score normalizado do ramo:

| λ | ramo@1 | Δ vs λ=0 | IC do Δ |
|---|---|---|---|
| 0,00 | 0,739 | — | — |
| 0,02 | 0,739 | 0,000 | −0,043..+0,043 |
| 0,05 | 0,761 | +0,022 | −0,033..+0,076 |
| 0,10 | 0,761 | +0,022 | −0,033..+0,076 |
| 0,20 | 0,772 | +0,033 | −0,022..+0,087 |

**Validação aninhada** (λ escolhido em 4/5, medido no 1/5): 70/92 = **0,761** contra 0,739
do `max` sem prior. O ganho é de 2 questões em 92 e o IC inferior fica abaixo de zero.

Decisão: **não adotar**. É um parâmetro a mais, ajustado em 92 questões, com efeito dentro
do ruído; e a informação de disciplina já entra na confiança pela feature `disc_match`.
Fica registrado como o único ganho grátis que sobrou — se a folha-verdade crescer, é o
primeiro candidato a testar.

## Estágio 2 — subtema dentro do ramo

| métrica | valor |
|---|---|
| top-1 restrito ao ramo acerta o tema central | 41/92 = 0,446 |
| top-1 restrito acerta pela régua do caso | 62/92 = 0,674 |
| casos em que publicar o subtema salvaria um ramo errado | **0** |

O estágio 2 não pode ajudar a publicar: a régua aceita pai e filho, então publicar o ramo
é sempre pelo menos tão correto quanto publicar o subtema, e o subtema adiciona o risco de
cair no irmão. Publicar subtema só faria sentido com um alvo de granularidade, que o case
não pede.

**Conclusão dos dois estágios:** a cascata não melhora a decisão. O sistema responde no
nível do ramo e o ranqueamento plano já entrega esse nível. A cascata fica no código como
diagnóstico (mede a granularidade disponível: 44,6% de acerto no subtema), não como regra.

## Estabilidade — o efeito colateral que importa

Trocar o texto do tema por `enri` muda o ranking inteiro: **266/659 = 40,4%** das questões
passam a ter outro ramo no top-1. O ganho de `ramo@1` (0,630 → 0,739) não é um ajuste fino;
é um novo ranking.

A medida mais direta de instabilidade veio da correção de taxonomia (v02). Mexer em **três
nós** — 5148 e 5156 reparentados sob 5155, e 5156 reescrito porque descrevia o instituto
errado — mudou (na versão com `lei_match`, antes da correção da feature):

| grandeza | efeito |
|---|---|
| temas previstos diferentes (659) | **8** |
| decisões que mudam (659) | **18** |
| publicações perdidas | 15 |
| publicações ganhas | 3 |
| perdas em que o tema previsto também mudou | **0** |

Ou seja: nenhuma das 15 perdas trocou de tema. Todas atravessaram o limiar pela confiança,
não pela busca. É a demonstração mais limpa de que a instabilidade mora na **camada de
decisão** — e é isso que o próximo ciclo deve atacar (diagnóstico de recuperação × decisão,
robustez da regra), não o vocabulário dos temas.

Números correlatos:

| grandeza | valor |
|---|---|
| `ramo@1` base → enriquecido | 0,630 → 0,739 |
| publicadas (659) | 130 (v01) → **115 (v02, após remover o `lei_match`; 118 antes)** |
| precisão in-sample | 19/20 = 0,950 |
| precisão aninhada corrigida | 13/17 = 0,765 |
| cobertura fora da folha | 94/559 = 0,168 |

A comparação base × enriquecido **de decisões** (não só de ramo) foi medida na v01
(177/659 mudavam) e não foi refeita após a v02: refazê-la é o primeiro item do próximo
ciclo, porque exige rodar o modelo de confiança com o texto base — um caminho que hoje não
está exposto no código.

## Risco a declarar

Com 100 rótulos, a leitura aninhada honesta é 13/17 = 0,765, com IC de Wilson [0,53; 0,90].
A instabilidade — 18 decisões movidas por uma correção que não mudou tema nenhum — mostra
que o sistema opera numa faixa de margens pequenas. Isso não invalida o 0,95 in-sample, mas
impede tratá-lo como garantia; é exatamente a limitação que a Etapa 6 (auditoria) registra
com 100 rótulos.

Se o critério do case fosse "publicar o mesmo conjunto com 95%", o enriquecimento seria
rejeitado por instabilidade. Como o critério é precisão e cobertura, ele entra, e a
instabilidade vira uma linha do relatório, não uma nota de rodapé.
