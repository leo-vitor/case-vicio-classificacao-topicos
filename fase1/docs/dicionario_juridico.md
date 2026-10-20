# Dicionário de enriquecimento jurídico (Fase 1)

## O que é

Um mapeamento **Key-Value** que traduz referências da questão ("Lei 11.340", "delação")
para os termos que **de fato aparecem** nos títulos da árvore ("Lei Maria da Penha",
"Colaboração Premiada"). Esses termos são **adicionados à consulta** antes da busca.

Por quê: a busca é lexical (TF-IDF/BM25). Se a questão cita um número de lei e o tema tem
o **apelido** da lei, não há coincidência de palavras — e o tema certo não entra na lista.
O dicionário fecha esse descompasso.

Arquivo: `data/dicionario_juridico.csv` (62 entradas). Código: `src/dicionario.py`.

## Regras de curadoria (deliberadamente conservadoras)

1. **Pequeno e conferido à mão.** Cada entrada foi checada contra os títulos reais de
   `data/temas.csv`. **Não** usamos LLM para gerar centenas de associações.
2. **Referências explícitas primeiro** (números de lei, nomes oficiais); sinônimos depois.
3. **Nada de mapear questão → resposta.** Mapeamos *citação jurídica → nome canônico*
   (ex.: "11.340" → "Lei Maria da Penha"), que é o uso do Vade Mecum — não a resposta.

Formato:

```csv
tipo,chave,termos
lei,11.340,Lei Maria da Penha violência doméstica familiar
sinonimo,delação,Colaboração Premiada
```

- `chave`: substring procurada no texto da questão (comparação sem acento e sem maiúsculas);
- `termos`: texto somado à consulta quando a chave casa.

## Como funciona no código

```
from src.dicionario import Dicionario
d = Dicionario()
d.expandir("... com base na Lei 11.340 ...")   # -> texto + "Lei Maria da Penha violência..."
```

No avaliador, a flag `+dic` liga o enriquecimento: `tfidf+irmao+dic`.

## Resultado (k=10)

| Config | `recall_hier` (93) | Legislação Especial |
|---|---|---|
| tfidf+filho (atual) | 0,667 | 5/19 |
| tfidf+top+dic | 0,731 | 12/19 |
| tfidf+irmao | 0,882 | 9/19 |
| **tfidf+irmao+dic** | **0,957** | **16/19** |

Confirmado em dev × holdout (`recall_hier`): filho 0,694/0,613 → irmao+dic **0,952/0,968**.
Legislação Especial no holdout: **2/6 → 6/6**. O ganho **não** é sobreajuste aos erros
conhecidos. (Versão atual do dicionário: `4de77271944d`, 62 entradas.)

Dois efeitos distintos:
- **Sozinho** (`+top+dic`), o dicionário sobe o piso sem aumentar a lista (10 candidatos).
- **Combinado** com irmãos, soma ganhos: o dicionário resolve o *vocabulário*, os irmãos
  resolvem a *estrutura*.

## Riscos e limitações

- **Casamento frágil.** A entrada `associação criminosa → Organizações Criminosas` ajuda
  em um erro conhecido, mas "associação criminosa" e "organização criminosa" são conceitos
  distintos — pode **piorar** outros casos. Foi mantida, mas é a candidata número 1 a revisão.
- **Manutenção manual.** Escala mal sem curadoria; não é "gerar 5.000 sinônimos com LLM".
- **Vade Mecum** (o corpus completo) é a versão em escala desta ideia — exige curadoria e
  licenciamento; fica como passo seguinte.
- **Alvo que não existe na árvore.** A entrada `estatuto da pessoa idosa` aponta para um
  título que **não existe**: o tema real é `Estaturo de Idoso - Crimes` (erro de digitação
  na própria origem). Só o termo "idoso" casa — vale corrigir o título na fonte.
- Recall maior **não garante** precisão maior; e adotar no pipeline invalida o cache do juiz.
