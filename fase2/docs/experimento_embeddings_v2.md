# Experimento 2 — embeddings densos com temas enriquecidos (pré-registro)

**Data do pré-registro:** 21/10/2026, antes de codificar os temas.
**Status:** pré-registrado; resultado abaixo, sem alteração do critério.

## Pergunta

O teste anterior de embeddings usou os temas **sem** o texto enriquecido e comparou
com a busca lexical já enriquecida. Isso é uma comparação injusta: o embedding via
o texto cru, enquanto o léxico via sinônimos, institutos e o texto do enriquecimento.
A pergunta agora é estreita:

> Com o **mesmo texto enriquecido** nos temas, o embedding denso supera a busca
> lexical atual no ramo do top-1?

Não é uma nova arquitetura. É uma repetição controlada, uma vez, com o critério
abaixo escrito antes do resultado.

## Desenho fixo

- Modelo: `intfloat/multilingual-e5-large` (local, MPS, offline).
- Questões: as 100 da folha; vetores já em cache com prefixo `query: `.
- Temas: os 371 publicáveis; texto enriquecido `caminho + título + sinônimos +
  institutos + texto_enriquecido` (o mesmo da busca lexical).
- Duas variantes de prefixo para os temas:
  1. `passage: ` — prefixo correto do e5 para documento; corrige só a injustiça
     do texto cru.
  2. `query: ` — corrige o texto e também o prefixo; variante exploratória.
- Para cada variante, medir:
  - **sozinha**: top-1 da similaridade cosseno questão × tema;
  - **em fusão RRF** com a matriz `rrf_all` atual (a busca lexical da entrega).
- Métrica primária: `ramo@1` com a **regra do pai** (`tema1`: se o top-1 é
  subtema, vale o pai de nível 1), nas **92 questões com tema**. As 8 fora da
  taxonomia ficam de fora, como em todos os experimentos.
- Métricas secundárias: `ramo@5`, `ramo@10`, `exato@1` (sem promoção), quebra por
  disciplina e flips por questão. Nenhuma delas decide a adoção.

## Critério de adoção (escrito antes)

Uma variante só é adotada se **as duas condições** valerem contra o `rrf_all`
atual, nas 92 questões:

1. **Ganho líquido de pelo menos 5 questões** no `ramo@1`:
   `acertos(variante) - acertos(rrf_all) >= 5`.
2. **Intervalo pareado de 95% inteiramente acima de zero** para a diferença
   pareada `variante - rrf_all` (bootstrap de 2.000 reamostragens das questões,
   semente 42): limite inferior > 0.

Se qualquer condição falhar, a variante **não é adotada**. O resultado fica
documentado; o relatório passa a dizer “embeddings, mesmo com os temas
enriquecidos, não superaram a busca lexical” em vez de “embeddings pioram”.

Não há ajuste de limiar, escolha de subconjunto, remoção de questões ou segunda
tentativa depois de ver o resultado. As duas variantes e as duas formas de uso
(sozinha/fusão) são as quatro comparações pré-registradas; não se acrescenta uma
quinta depois.

## Custos e consequências

- O teste é barato: as 100 questões já estão em cache; só os 371 temas são
  recodificados, duas vezes (poucos minutos no Mac).
- **Se adotar**, os vetores das 659 questões teriam de ser versionados para o
  avaliador regenerar sem rodar modelo; o README ganha uma linha dizendo que os
  embeddings são cache derivado do texto das questões. Também seria preciso
  refazer a confiança e regenerar `publicacao.csv` e `previsao.txt`.
- **Se não adotar**, nada no pipeline muda; só o texto do relatório e este
  registro.

## Saídas

- `artefatos/embeddings_v2_por_questao.csv` — uma linha por questão, com top-1,
  ramo, rank e acerto de cada variante e do baseline.
- `artefatos/embeddings_v2_resumo.csv` — uma linha por variante, com acertos,
  delta, IC pareado, flips e decisão.
- `artefatos/embeddings_v2_resumo.json` — metadados, hashes dos textos/caches e
  critério.
- `src/embeddings_v2.py` — script que reproduz o teste.

## Resultado

**Executado em 21/10/2026, depois do pré-registro acima.** O critério não foi alterado.

| variante | acertos | ramo@1 | delta vs. `rrf_all` | IC pareado 95% | ganhas/perdidas | adotar |
|---|---:|---:|---:|---:|---:|---|
| `rrf_all` (baseline) | 68/92 | 0,739 | — | — | — | — |
| `emb_passage` (sozinho) | 49/92 | 0,533 | −0,206 | [−0,304; −0,109] | 3/22 | não |
| `rrf_emb_passage` | 66/92 | 0,717 | −0,022 | [−0,098; +0,054] | 5/7 | não |
| `emb_query` (sozinho) | 63/92 | 0,685 | −0,054 | [−0,141; +0,033] | 6/11 | não |
| `rrf_emb_query` | **69/92** | **0,750** | **+0,011** | **[−0,054; +0,076]** | 5/4 | não |

**Nenhuma variante passa.** A melhor (`rrf_emb_query`) ganha **1 questão**, não 5, e o IC
pareado cruza zero (McNemar p = 1,0). `emb_passage` é muito pior; `emb_query` melhora o
embedding sozinho, mas ainda fica abaixo do léxico. Com o mesmo texto enriquecido, a
“injustiça” do texto cru não explica a derrota: **o embedding não supera a busca lexical
no top-1**, embora o recall no top-10 seja alto (0,89–0,96).

A quebra por disciplina mostra por que a fusão com `query` não é robusta: ela ganha
+3 em Processo Penal e +1 em Penal, mas perde −3 em Legislação Especial; o líquido é +1.
Os detalhes estão em `artefatos/embeddings_v2_por_disciplina.csv`.

**Decisão:** não adotar. `publicacao.csv`, `previsao.txt` e o pipeline ficam intactos.
O relatório passa a dizer “embeddings, mesmo com os temas enriquecidos, não superaram a
busca lexical” — não “embeddings pioram”. O custo foi ~52 s na primeira execução (duas
codificações de 371 temas) e ~3 s nas seguintes, com cache; 351 dos 371 temas têm
enriquecimento, os 20 restantes usam o texto base.

