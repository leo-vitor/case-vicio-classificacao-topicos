# Experimento 4 — revisão jurídica humana (30 objetos)

O enriquecimento é gerado por LLM offline; a pergunta não é se o texto "parece bom", é se um
**jurista** reconhece ali o instituto do título e os termos que um examinador usaria. Não vale
concordância entre IAs: a revisão é humana, cega e com rubrica fixa.

A amostra e o critério de aceitação estão **pré-registrados** abaixo. Nada muda depois de ver
o resultado.

## Amostra (30 objetos de 351)

| estrato | n | por quê |
|---|---|---|
| colisões entre irmãos | 8 | onde o vocabulário pode ter vazado entre temas parecidos |
| taxonomia v02 (5148, 5155, 5156) | 3 | nós reparentados/reescritos; maior risco de erro novo |
| Legislação Especial | 6 | disciplina menos representada e a de pior `ramo@1` |
| Criminologia | 5 | disciplina menor, vocabulário menos técnico |
| Penal | 3 | maior estrato, usado como controle |
| Processo Penal | 2 | segundo maior estrato |
| aleatórios | 3 | cobertura de temas fora dos estratos acima |

Gerado por `python -m src.amostra_revisao` (seed fixa): `artefatos/revisao_30.csv` (controle) e
`artefatos/revisao_30_cego.csv` (folha do revisor).

## Desenho cego

- A folha do revisor **não** traz estrato, confiança do modelo, decisão do pipeline nem o
  gabarito. A ordem é aleatória.
- No fim da folha há **3 duplicatas** (linhas 31–33) do mesmo objeto, sem indicação de qual
  é a duplicata. Servem para medir a consistência intra-revisor: se as duas notas diferirem
  mais de 1 ponto em qualquer dimensão, a rubrica não está sendo aplicada de forma estável.
- O revisor não deve abrir `publicacao.csv`, `previsao.txt`, os relatórios nem conversar com
  outra IA sobre os objetos.

## Rubrica (0–2 por dimensão)

| dimensão | 0 | 1 | 2 |
|---|---|---|---|
| **R1. Precisão jurídica** | há erro de direito (termo/instituto não corresponde ao título) | impreciso ou incompleto, sem erro grave | os termos e o texto correspondem ao instituto |
| **R2. Discriminação** | os termos serviriam a qualquer irmão | parcialmente específicos | distinguem este tema dos irmãos |
| **R3. Cobertura lexical** | um examinador não usaria esses termos | alguns usaria | é assim que a questão seria cobrada |
| **R4. Risco de confusão** | algum termo puxa claramente para outro ramo | risco possível | não há risco |

`veredito`: **manter** (soma ≥ 6 e nenhuma dimensão 0), **corrigir** (soma 4–5, ou uma
dimensão 0 isolada), **refazer** (soma ≤ 3, ou R1 = 0, ou R4 = 0).

`comentario`: livre, obrigatório para `corrigir` e `refazer` (o que está errado e qual seria o
termo correto).

## Critério de aceitação (pré-registrado)

| resultado | decisão |
|---|---|
| ≥ 27 objetos `manter`/`corrigir` | artefato mantido; corrigem-se os objetos apontados |
| 1–2 objetos `refazer` | reescrever os objetos e revalidar o contrato |
| ≥ 3 objetos `refazer` | ampliar a amostra para 60 antes de decidir |

A consistência das 3 duplicatas entra como controle de qualidade: diferença > 1 em qualquer
dimensão invalida a rodada e a rubrica é reexplicada.

## O que a revisão NÃO prova

- Não certifica 95% de precisão: 30 objetos não sustentam isso (Wilson inferior de 27/30 é
  ~0,74). Ela valida a **qualidade do insumo**, não a taxa de acerto do classificador.
- Não substitui a folha-verdade: o revisor avalia o texto do tema, não a predição.
- Não autoriza "concordância entre IAs" como evidência: se não houver revisor humano, o
  experimento fica **bloqueado** e assim é declarado.

## A amostra

| ordem | id | título | estrato |
|---|---|---|---|
| 1 | 4699 | Identificação Criminal | legislação especial |
| 2 | 5549 | Declaração do Ofendido | colisão (5546/5549) |
| 3 | 5148 | Dos Crimes contra as Instituições Democráticas | taxonomia v02 |
| 4 | 5472 | Ação Penal de Iniciativa Privada | colisão (5469/5472) |
| 5 | 5156 | Dos Crimes contra o Funcionamento dos Serviços Essenciais | taxonomia v02 |
| 6 | 4385 | Teorias Sociológicas Explicativas da Criminalidade | criminologia |
| 7 | 5094 | Contrabando ou Descaminho | penal |
| 8 | 5570 | Recurso Extraordinário | colisão (5570/5571) |
| 9 | 4382 | Métodos e funções da Criminologia | criminologia |
| 10 | 5146 | Crimes Contra à Paz Pública | penal |
| 11 | 5522 | Medidas Cautelares Diversas da Prisão | colisão (5522/5523) |
| 12 | 5469 | Princípios da Ação Penal | colisão (5469/5472) |
| 13 | 4386 | Teorias de Nível Individual | criminologia |
| 14 | 5515 | Efeito dos Recursos | processo penal |
| 15 | 5571 | Recurso Especial | colisão (5570/5571) |
| 16 | 5546 | Perícia | colisão (5546/5549) |
| 17 | 4389 | Vitimologia | criminologia |
| 18 | 5175 | Iter Criminis | aleatório |
| 19 | 5125 | Dos Crimes Contra a Incolumidade Pública | penal |
| 20 | 4708 | Tráfico de Drogas | legislação especial |
| 21 | 5155 | Dos Crimes contra o Estado Democrático de Direito | taxonomia v02 |
| 22 | 5173 | Interpretação da Norma Penal | aleatório |
| 23 | 4383 | Teorias e Síndromes com Enfoque nas Vítimas | criminologia |
| 24 | 5544 | Cadeia de Custódia | processo penal |
| 25 | 4701 | Juizado Especial Criminal | legislação especial |
| 26 | 4685 | Biossegurança | legislação especial |
| 27 | 4706 | Terrorismo | legislação especial |
| 28 | 5205 | Penas Restritivas de Direitos | aleatório |
| 29 | 4694 | Crimes previstos no CDC | legislação especial |
| 30 | 5523 | Liberdade Provisória | colisão (5522/5523) |

Duplicatas cegas: 16, 24 e 28 (linhas 31–33 da folha).

## Instruções ao revisor (≈ 30 min)

1. Abra só `artefatos/revisao_30_cego.csv`.
2. Para cada linha, leia o título e os campos gerados; dê nota 0–2 nas quatro dimensões.
3. Escreva o veredito e, se for `corrigir`/`refazer`, o termo que deveria estar ali.
4. Não consulte o pipeline, o gabarito nem outra IA.
5. Ao chegar às linhas 31–33, responda sem olhar as anteriores.

## Leitura do resultado

- **Aprovado:** relatório cita a revisão como validação do insumo (30 objetos, X/30), sem
  convertê-la em precisão do classificador.
- **Reprovado:** os objetos apontados são reescritos, o contrato roda de novo (segundos) e a
  amostra é revalidada; o pipeline (~30 s) é reexecutado e os números do relatório são
  atualizados. O custo de corrigir é baixo; o custo de publicar um erro jurídico não.
- **Sem revisor:** o experimento fica declarado como pendente no relatório. Não se substitui
  por concordância entre modelos.
