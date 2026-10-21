# Experimento 1 — recuperação × decisão

Pergunta: quando a regra erra, o ramo certo **não estava lá** (gargalo de busca) ou
**estava e a decisão não aproveitou** (gargalo de decisão)?

Reproduz com `python -m src.diagnostico` (~30 s). Artefato: `artefatos/diagnostico.json`.
Toda tabela abaixo é gerada com **denominadores explícitos, categorias mutuamente exclusivas
e cada questão exatamente uma vez** (asserções no código: ids únicos, crosstab = 92,
categorias = 92).

## Base

| grandeza | valor |
|---|---|
| folha-verdade | 100 |
| válidas (com tema) | **92** |
| `fora_da_taxonomia` | 8 |
| regra | consenso ≥ 0,75 e `p` ≥ 0,887009 (a do entregável) |

Rank = posição, no ranking do `rrf_all` enriquecido, do **primeiro item cujo ramo está entre
os aceitos** pela régua (tema central ou extra, promovidos ao nível 1).

## Recuperação × decisão (92 válidas)

| rank do ramo certo | publicar | revisar | total |
|---|---|---|---|
| top-1 | 20 | **48** | 68 |
| top-2 a 5 | 0 | 18 | 18 |
| top-6 a 10 | **1** | 0 | 1 |
| fora do top-10 | 0 | 5 | 5 |
| **total** | **21** | **71** | **92** |

Categorias exclusivas (somam 92):

| categoria | n |
|---|---|
| publicado e certo | 20 |
| publicado e errado | **1** |
| revisado, top-1 no ramo certo | **48** |
| revisado, ramo certo no top-2 a 10 | 18 |
| revisado, ramo ausente do top-10 | 5 |

**Leitura.** O gargalo principal é a **decisão**, não a busca: em 68/92 = 73,9% o ramo certo
já é o top-1, e a regra manda **48** dessas para revisão. A busca é o gargalo para apenas
5/92 = 5,4% (ramo ausente do top-10: Q0028, Q0290, Q0316, Q0324, Q0338). O top-10 cobre
87/92 = 94,6% — o teto de recuperação não é o problema.

O único erro **publicado** na folha é Q0202: ramo certo em **10º**, `p_oof` = 0,967 e
consenso = 1,0. É o modo de falha esperado de uma confiança montada em margens: um top-1
com margem grande parece seguro mesmo quando o ramo certo está longe. Nenhuma feature do
modelo vê "o ramo aceito está no rank 10" — e não deve ver, porque o gabarito não está
disponível em produção. O que dá para fazer é calibrar melhor o topo e usar o rank como
feature de *incerteza* (distância até o 2º ramo), não como rótulo.

## Por disciplina (92 válidas)

| disciplina | n | publicadas | acertos | revisadas com top-1 certo |
|---|---|---|---|---|
| Penal | 40 | 10 | 9 | 22 |
| Processo Penal | 30 | 8 | 8 | 14 |
| Legislação Especial | 12 | 1 | 1 | 5 |
| Criminologia | 10 | 2 | 2 | 7 |

Criminologia é onde a camada de confiança é mais conservadora (7 de 10 revisadas já tinham o
top-1 certo); Penal concentra o único erro publicado.

## Denominadores (por que 20, 21 e 118 aparecem juntos)

| denominador | publicadas | acertos | precisão | cobertura |
|---|---|---|---|---|
| in-sample, `p_oof` (modelos de 80) | 20 | 19 | 0,950 | 0,20 |
| entregue, `p_all` na folha | 21 | 20 | 0,952 | 0,21 |
| entregue, 659 | 118 | — | — | 0,179 |
| fora da folha (559) | 97 | sem rótulo | — | 0,174 |

A diferença de 20 para 21 é **uma** questão, Q0035: `p_oof` = 0,502 (revisar) e `p_all` =
0,960 (publicar, acertou). O `p_all` vem do modelo treinado nos 100, que **viu o rótulo de
Q0035**; o `p_oof` não. O número honesto para a folha é 20/19 = 0,950; o entregável usa
`p_all` porque é o modelo disponível para as 659. Os dois ficam rotulados — nunca somados.

## O que isso muda no plano

1. **Não investir em recuperação agora.** O top-10 já cobre 94,6%; trocar recuperador
   ganharia no máximo ~5 questões, e os testes pareados (Experimento 3) já mostram empate
   entre `char` e `rrf_all`.
2. **Atacar a camada de decisão.** 48 publicações corretas são perdidas por falta de
   confiança. O caminho é calibrar o topo (mais rótulos no intervalo 0,5–0,9) e testar
   features de **margem entre ramos** (`branch_gap`) e de **estabilidade entre
   recuperadores** — não novas regras manuais.
3. **Vigiar o falso positivo.** Q0202 mostra que confiança alta não protege contra rank
   distante; a fila de revisão deve priorizar `rank_ramo` alto entre as publicadas de alta
   confiança, mesmo que poucas.
