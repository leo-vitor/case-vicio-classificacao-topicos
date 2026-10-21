# Briefing — enriquecimento jurídico da taxonomia (Fase 2)

Documento de hand-off. Contém tudo que é preciso para gerar o artefato de enriquecimento
**sem** acesso às questões, ao gabarito ou ao código de produção.

---

## 0. Em uma frase

Precisamos que cada um dos **371 temas publicáveis** receba um texto enriquecido —
**curto, discriminativo e versionado** — para melhorar o ranqueamento lexical de questões
de concurso jurídico. A entrega é um **artefato estático** (JSON Lines) + o script que o
gerou + o validador. Nada de código de produção, nada de modelo em runtime.

## 1. Como o sistema funciona hoje (e onde dói)

O pipeline é **recuperação de informação lexical + regra seletiva**. Não existe
classificador de classes, não existe `retriever.py` nem `classifier.py`, e nenhum modelo
de linguagem roda na execução.

**Contrato do texto do tema** (`src/recuperacao.py`):

```python
def texto_tema(arv, tid):
    # caminho completo + título — nada mais
    return arv.caminho[tid].replace(">", " ") + " " + arv.titulo[tid]
```

Exemplo: `4371` →
`'Criminologia   Etapas Evolutivas e Escolas Criminológicas Etapas Evolutivas e Escolas Criminológicas'`
— **100 caracteres** (o caminho é repetido no texto porque o título já aparece nele).
No conjunto dos 371 publicáveis, a média é **93,7 caracteres** (mínimo 29, máximo 315).
Os enunciados têm milhares. É aí que o *vocabulary mismatch* aparece.

**Índices** (3 recuperadores + fusão por RRF):

| Recuperador | Definição |
|---|---|
| `tfidf` | TF-IDF palavra, ngram 1–2, sublinear, sem acento |
| `tfidf_char` | TF-IDF `char_wb`, ngram 3–5 (tolera ruído de digitação/morfologia) |
| `bm25` | Okapi BM25, k1=1,5, b=0,75 |
| `rrf_tfidf_bm25` | RRF(tfidf, bm25), k=60 |
| `rrf_all` | RRF(tfidf, char, bm25) — **recuperador primário** |

Os vetorizadores são ajustados **apenas no corpus de 371 temas** (não no conjunto
questão+tema), para que a configuração possa ser aplicada a uma questão nova sem refit.

**A régua do case:** publicar no tema central, num tema extra, ou num **pai** ou **filho**
direto conta como acerto. Irmão conta como **erro**. Consequência prática: como a regra do
pai promove todo top-1 de nível 2 ao seu pai de nível 1, **o sistema sempre publica um tema
de nível 1**. Ou seja, o que importa não é acertar o subtema, é acertar o **ramo**.

**Diagnóstico medido** (92 questões rotuladas com tema, fora da dobra):

| Recuperador | ramo@1 | ramo@3 | ramo@5 | ramo@10 |
|---|---|---|---|---|
| `rrf_all` | **0,641** | 0,804 | 0,837 | **0,935** |
| `tfidf_char` | 0,554 | 0,870 | 0,902 | 0,935 |
| `tfidf` | 0,641 | 0,761 | 0,804 | 0,902 |
| `bm25` | 0,500 | 0,685 | 0,739 | 0,804 |

*ramo@k = o tema de nível 1 correto (ou o pai do tema central) está entre os k primeiros.*

Leitura: o teto do ranqueamento é **0,935** (ramo@10) e o ponto de partida é **0,641**
(ramo@1). Há folga grande, e ela está no **texto dos temas** — exatamente o que este
briefing pede. Recall do tema *exato*: 0,68 no top-5 e 0,74 no top-10 (`rrf_all`).

**Como o erro se distribui** (41 erros em 100):

| Bucket | n |
|---|---|
| gold fora da taxonomia | 8 |
| **outro tema de nível 1 no mesmo ramo** | 13 |
| **outra disciplina** | 13 |
| outros (mesmo ramo, não relacionado) | 7 |

Dois casos que orientam o enriquecimento:

- **Legislação Especial:** acerto de ramo 0,417 e **8 dos 12 erros são cross-disciplina** —
  o sistema manda essas questões para Penal/Processo Penal. É a fronteira a tratar.
- **Criminologia:** consenso total entre recuperadores em 10/10, mas só 70% de acerto —
  aqui o erro é *dentro* da disciplina, entre temas vizinhos. É onde **distinções** ajudam.

## 2. Restrições inegociáveis

1. **Nenhum modelo de linguagem na execução.** O enriquecimento é gerado **offline** e
   versionado; a produção apenas lê o arquivo.
2. **Zero vazamento.** As questões e o gabarito **não** são enviados e não podem ser
   usados para calibrar vocabulário. A única fonte é a taxonomia + o dicionário do case.
   Se você precisar do corpus de questões para "ajustar termos", essa é a fronteira que
   não cruzamos.
3. **Sem invenção.** Leis apenas da whitelist (seção 5); ids apenas os da taxonomia.
4. **Discriminativo, não exaustivo.** Texto gordo piora o resultado: dilui o cosseno do
   TF-IDF e desequilibra a normalização de comprimento do BM25. Descrever bem um tema pode
   fazê-lo atrair questões vizinhas. Teto de tamanho na seção 4.
5. **Campos atômicos e separáveis.** Vamos testar variantes por ablação (só sinônimos;
   só descrição; descrição + distinções). Um campo único de prosa impede isso.

## 3. Entrada

**Anexo 1 — `temas_para_enriquecimento.csv`** (377 linhas, uma por nó da árvore).
Está em `artefatos/temas_para_enriquecimento.csv` (derivado de `data/temas.csv`, o anexo do
enunciado). Para reproduzir:

```bash
.venv/bin/python -c "import pandas as pd; t=pd.read_csv('data/temas.csv',dtype=str).fillna(''); t[['tema_id','parent_id','disciplina','nivel','titulo','caminho','status']].to_csv('artefatos/temas_para_enriquecimento.csv',index=False)"
```

| Coluna | Exemplo |
|---|---|
| `tema_id` | `4371` |
| `parent_id` | `4365` |
| `disciplina` | `Criminologia` |
| `nivel` | `1` |
| `titulo` | `Etapas Evolutivas e Escolas Criminológicas` |
| `caminho` | `Criminologia > Etapas Evolutivas e Escolas Criminológicas` |
| `status` | `active` |

Estrutura: **4 raízes (nível 0)** — `Criminologia`, `Penal`, `Processo Penal`,
`Direito Penal - Legislação Especial`; **109 temas de nível 1**; **262 subtemas de nível 2**.
Publicáveis: 371 (tudo de nível ≥ 1 e `status = active`). Dos 109 temas de nível 1, **51
têm filhos** (média 5,1; máximo 16). Os 2 nós `inactive` **não** devem ser enriquecidos
(podem ser ignorados na saída). O campo `descricao` do CSV original foi omitido de
propósito: é metadado de origem, sem valor semântico.

> **Atualização (geração):** 20 nós de nível 1 duplicados, sem filhos e sem descrição
> (6716–6728 e 6732–6738) foram **excluídos** do enriquecimento — não têm o que enriquecer
> e viram filtro de disciplina no passo 5. O universo efetivo é **351 objetos**. Onde este
> documento diz 371, leia-se 371 publicáveis menos os 20 excluídos.

**Anexo 2 — `dicionario_juridico.csv`** (62 linhas: **21 de tipo `lei`**, **41 de tipo
`sinonimo`**). É o vocabulário jurídico já curado no projeto — mas aplicado **ao lado da
questão**. Este trabalho leva o mesmo vocabulário para o **lado do tema**.

Exemplos:

```
tipo,chave,termos
lei,11.340,Lei Maria da Penha violência doméstica familiar medidas protetivas ...
lei,8.072,Crimes Hediondos hediondo
sinonimo,hediondo,Crimes Hediondos
sinonimo,anpp,Acordo de Não Persecução Penal
```

Use-o como fonte: (a) não repita sinônimos que já estão lá; (b) as chaves de tipo `lei` são
a whitelist de leis.

## 4. Saída exigida

**JSON Lines**, um objeto por tema do universo enriquecível (351 objetos; ordem livre; `\n` entre
objetos). O arquivo de trabalho é `fase2/enriquecimento_v01.jsonl` (parcial, em geração); o
entregável final vai para `data/enriquecimento_v1.jsonl` (versionado no repositório, como já
acontece com o dicionário).

```json
{
  "id_tema": "4371",
  "titulo": "Etapas Evolutivas e Escolas Criminológicas",
  "sinonimos": ["escolas penais", "positivismo criminológico", "escola clássica",
                "terza scuola", "escola de Chicago"],
  "institutos": ["Lombroso", "Ferri", "Garofalo", "garantismo penal"],
  "leis": [],
  "distincoes": [
    {"id_tema": "4372",
     "diferenca": "trata da periodização histórica (Antiguidade, Idade Média, Moderna); este tema trata das correntes doutrinárias"}
  ],
  "texto_enriquecido": "Correntes doutrinárias da criminologia (clássica, positivista, terza scuola) e a periodização histórica do pensamento criminológico."
}
```

Regras de cada campo:

| Campo | Regra |
|---|---|
| `id_tema`, `titulo` | copiados do anexo 1, sem alteração |
| `sinonimos` | **2–5** formas como o examinador escreveria, ≤ 40 caracteres cada. Não repetir o título. O piso original era 3; foi relaxado para 2 durante a geração porque nenhuma métrica depende dele e forçar um terceiro termo produz preenchimento. Volta a 3 se a ablação por campo mostrar ganho |
| `institutos` | 0–5 nomes próprios de institutos, doutrinas, autores ou princípios, ≤ 35 caracteres cada |
| `leis` | 0–4 chaves **existentes** no dicionário. `[]` é resposta perfeitamente válida |
| `distincoes` | 0–3 itens, `id_tema` **apenas de irmãos reais** (mesmo `parent_id`). Escreva o critério *jurídico* da diferença, não a diferença de palavras |
| `texto_enriquecido` | **120–250 caracteres**, 2 frases. Deve dizer o que distingue o tema dos vizinhos. Sem jurisprudência, sem número de julgado, sem URL |

A faixa de 120–250 caracteres não é arbitrária: hoje um documento de tema tem 94 em média, e o
objetivo é *acrescentar* vocabulário, não substituir o título — daí um teto de aproximadamente o
dobro do tamanho atual e um piso que garanta conteúdo além do título. O contrato verificado é o
dos limites **por campo**; o teto de 700 caracteres por linha foi descartado por conflitar com
títulos longos e duas distinções.

O texto que será indexado é montado por nós, campo a campo
(`caminho + titulo + sinonimos + institutos + texto_enriquecido`), justamente para permitir
a ablação. Não concatene nada você mesmo.

**Piloto antes do lote completo:** entregue primeiro **10 temas** (2 por disciplina,
escolhidos por você) para revisão. Só depois dos ajustes gere os 351. Isso evita 351 linhas
do formato errado.

## 5. Regras de anti-alucinação (verificáveis por script)

1. `leis` ⊆ whitelist do dicionário (as 21 chaves de tipo `lei`). Qualquer outra coisa é
   rejeitada pelo validador.
2. `distincoes[].id_tema` deve existir na taxonomia **e** ter o mesmo `parent_id` do tema
   (irmão real). Ids inexistentes ou primos são rejeitados.
3. Nenhum campo pode conter número de processo, julgado, súmula, data ou URL.
4. `texto_enriquecido` ≤ 300 caracteres (verificado; rejeita, não trunca).
5. Nenhum `id_tema` duplicado na saída; nenhum tema publicável ausente.
6. Sem caracteres de controle; UTF-8.

## 6. Como o artefato será avaliado

O experimento é: **congelar toda a decisão** (recuperadores, regra do pai, consenso,
limiar) e trocar **apenas** o texto do tema. Mesmos folds, sempre.

Pisos gratuitos que serão medidos **antes** (o enriquecimento precisa vencê-los):

| Piso | O que é |
|---|---|
| `+filhos` | anexar os títulos dos filhos ao documento do tema de nível 1 (dá ao ramo o vocabulário dos subtemas) |
| `+dicionario_tema` | aplicar ao lado do tema os 41 sinônimos e as 21 leis já curados |

Métricas, nesta ordem de importância:

1. **`ramo@1`** — é o que sustenta a régua literal. *Métrica de decisão, pré-registrada.*
2. `ramo@3` / `ramo@5`
3. recall do tema **exato** no top-5 e top-10
4. ao final, precisão e cobertura do sistema completo, com a regra congelada

**Critério de entrada:** `ramo@1` melhora **≥ +0,05** em relação ao melhor piso **e** a
precisão não cai com a cobertura fixada em 0,20. Abaixo disso, o enriquecimento não entra —
já tentamos da ordem de 100 configurações neste projeto e o erro padrão é acumular
complexidade por acaso.

Referência do estado atual (não alterar): decisão nas 659 questões → 131 publicar /
528 revisar; precisão 0,95 in-sample e 0,90 aninhada (sem vazamento), com 100 rótulos
sendo impossível certificar 95%.

## 7. O que esperamos de você

| Entregável | Formato |
|---|---|
| Piloto | 10 objetos, para revisão |
| Artefato completo | `enriquecimento_v1.jsonl` (351 objetos; em curso, 172 gerados) |
| Prompt de geração | texto versionado, com as regras da seção 5 explícitas |
| Script de geração | reproduzível, com o modelo/versão registrados no cabeçalho |
| Validador | Python puro, sem dependências novas: aplica os 6 itens da seção 5 e imprime um relatório (quantos temas sem sinônimos, quantas leis fora da whitelist, distribuição do tamanho do `texto_enriquecido`). Entregue em `src/validador_enriquecimento.py` + `scripts/ingerir.py` (`--auditar`, `--commit`) |

Não é necessário: código de produção, integração com o índice, `Pydantic`, banco de dados,
URLs de normas, campo de autoavaliação de confiança, ou qualquer coisa que só faça sentido
em runtime.

E uma observação de método: o enriquecimento **é uma hipótese sobre vocabulário**, não
sobre o direito. Se um tema for ambíguo na taxonomia, marque-o e nos diga — não invente
critério de desempate. Ambiguidade na taxonomia é um achado, não um problema a esconder.
