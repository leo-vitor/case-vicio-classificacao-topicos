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
| `media` (média do ramo) | 0,457 | 0,359–0,558 | −0,283 | −0,391..−0,185 |

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
| 0,05 | 0,739 | 0,000 | −0,043..+0,043 |
| 0,10 | 0,750 | +0,011 | −0,033..+0,054 |
| 0,20 | 0,761 | +0,022 | −0,033..+0,076 |

**Validação aninhada** (λ escolhido em 4/5, medido no 1/5): 69/92 = **0,750** contra 0,728
do `max` sem prior. O ganho é de 2 questões em 92 e o IC inferior fica abaixo de zero.

Decisão: **não adotar**. É um parâmetro a mais, ajustado em 92 questões, com efeito dentro
do ruído; e a informação de disciplina já entra na confiança pela feature `disc_match`.
Fica registrado como o único ganho grátis que sobrou — se a folha-verdade crescer, é o
primeiro candidato a testar.

## Estágio 2 — subtema dentro do ramo

| métrica | valor |
|---|---|
| top-1 restrito ao ramo acerta o tema central | 40/92 = 0,435 |
| top-1 restrito acerta pela régua do caso | 61/92 = 0,663 |
| casos em que publicar o subtema salvaria um ramo errado | **0** |

O estágio 2 não pode ajudar a publicar: a régua aceita pai e filho, então publicar o ramo
é sempre pelo menos tão correto quanto publicar o subtema, e o subtema adiciona o risco de
cair no irmão. Publicar subtema só faria sentido com um alvo de granularidade, que o case
não pede.

**Conclusão dos dois estágios:** a cascata não melhora a decisão. O sistema responde no
nível do ramo e o ranqueamento plano já entrega esse nível. A cascata fica no código como
diagnóstico (mede a granularidade disponível: 43,5% de acerto no subtema), não como regra.

## Estabilidade — o efeito colateral que importa

Trocar o texto do tema por `enri` muda o ranking inteiro:

| grandeza | base | enriquecido |
|---|---|---|
| temas atribuídos diferentes | — | **268/659 = 40,7%** |
| decisões que mudam | — | **177/659 = 26,9%** |
| publicadas em comum | 131 | 42 (32% das publicadas) |
| publicadas | 131 | 130 |
| precisão aninhada (100) | 13/15 = 0,867 | 32/34 = 0,941 |
| cobertura aninhada (100) | 0,15 | 0,34 |
| publicadas fora da folha | 111/559 = 0,20 | 108/559 = 0,19 |
| cobertura antigas vs novas | 0,14 vs 0,25 | **0,19 vs 0,20** |

Leituras:

1. O ganho de `ramo@1` **não** é um remendo local: 41% dos temas mudam de nome. O conjunto
   publicado é quase outro (só 42 em comum). Não é um ajuste fino — é um novo ranking.
2. A precisão estimada sobe (0,867 → 0,941 aninhada) e a cobertura aninhada dobra
   (0,15 → 0,34). Isso é o esperado se o top-1 passou a acertar mais: há mais positivos
   para o modelo aprender e menos falsos positivos a filtrar.
3. A discrepância entre questões antigas e novas **desaparece** (0,14/0,25 → 0,19/0,20).
   O enriquecimento deu vocabulário aos temas que os enunciados novos cobriam com outras
   palavras. É o efeito mais consistente da intervenção e o mais fácil de defender.
4. O número de publicadas não muda (131 → 130) porque o limiar conservador é re-escolhido
   a cada rodada para sustentar 95%. O que muda é **quais**.

## Risco a declarar

Com 100 rótulos, precisão de 0,94 em 34 publicadas tem IC de Wilson [0,81; 0,99]. A
instabilidade de 27% nas decisões significa que o sistema está operando numa faixa de
margens pequenas: pequenas mudanças de vocabulário movem questões através do limiar. Isso
não invalida o 95% medido, mas impede tratá-lo como garantia — é exatamente a limitação
que a Etapa 6 (auditoria) já registrava com 100 rótulos.

Se o critério do case fosse "publicar o mesmo conjunto com 95%", o enriquecimento seria
rejeitado por instabilidade. Como o critério é precisão e cobertura, ele entra, e a
instabilidade vira uma linha do relatório, não uma nota de rodapé.
