# Entrega da Fase 2 — pipeline, resultados e limites

Tudo reproduzível **sem rede e sem LLM** a partir dos anexos. Comando único:

```bash
cd fase2
.venv/bin/python -m src.baseline      # Etapa 1: baseline lexical
.venv/bin/python -m src.confianca     # Etapa 3: confiança no nível da questão
.venv/bin/python -m src.decisao       # Etapas 3/4: decisão seletiva -> publicacao.csv
.venv/bin/python -m src.previsao      # Etapa 5: previsao.txt
```

## O que a investigação mostrou

### 1. A régua do case premia o nó pai

Se o top-1 é um subtema (nível 2), publicar o **tema pai** (nível 1) nunca piora: a régua
aceita o pai, e o pai cobre também os irmãos. Medido nos 100:

| Recuperador | publicando o top-1 | promovendo nível 2 → pai | ganho | perda |
|---|---|---|---|---|
| tfidf | 56 | 59 | +3 | 0 |
| tfidf_char | 47 | 51 | +4 | 0 |
| bm25 | 42 | 46 | +4 | 0 |
| rrf_all | 56 | 59 | +3 | 0 |

Zero perdas em todos. É a regra mais barata do case.

### 2. O melhor recuperador é o TF-IDF de caracteres (mas o RRF decide melhor)

`tfidf_char` tem o melhor recall hierárquico no top-10 (0,91), porque os títulos da
árvore são curtos e o domínio é morfológico. Já para **top-1**, `rrf_all` (TF-IDF + BM25)
é o mais preciso (hier@1 = 0,61). Detalhes em [`etapa1_baseline.md`](etapa1_baseline.md).

### 3. Reranker de candidatos **não** ajudou — e isso está documentado

Rodei um reranker logístico sobre 16 features de candidato (posição, margem, relação
com o top-1, gêmeo, lei citada, prior). Resultado: melhor caso empata com a regra v0 e,
em geral, perde (0,49–0,58 contra 0,51–0,61). **Decisão: não entra na entrega** (regra de
parada: sem ganho, sem complexidade).

### 4. Embeddings densos também não — por ora

`intfloat/multilingual-e5-large` (local, MPS, vetores versionados): hier@10 = 0,79
isolado e 0,92 no híbrido com o char, mas **top-1 pior** (0,46–0,51). Como a decisão vive
do top-1, embeddings ficam de fora. `k`-NN entre questões (usando os rótulos) também foi
pior (0,43–0,48).

### 5. O que funcionou: **consenso entre recuperadores**

O sinal mais forte não é a similaridade, é a **concordância**. Publicar só quando os
quatro recuperadores promovem o *mesmo* nó corta o erro grosso:

| Consenso | n | precisão |
|---|---|---|
| 0,25 | 8 | 0,00 |
| 0,50 | 16 | 0,38 |
| 0,75 | 28 | 0,54 |
| **1,00** | **48** | **0,79** |

E o consenso pegou justamente os casos fora da taxonomia: 6 dos 8 `fora` ficam com
consenso ≤ 0,75 e são barrados automaticamente.

## Ponto de operação escolhido

**Publicar se consenso = 1,00 E confiança ≥ 0,872** (confiança = regressão logística
sobre 14 features de topo de ranking). Caso contrário, `revisar`.

| Leitura | Publicadas | Acertos | Precisão | IC 95% (Wilson) | Cobertura |
|---|---|---|---|---|---|
| In-sample (regra fixa) | 20 | 19 | 0,950 | 0,764–0,991 | 0,20 |
| Aninhada (limiar fora do grupo) | 15 | 13 | 0,867 | 0,621–0,974 | 0,15 |
| Publicando tudo | 100 | 59 | 0,590 | 0,492–0,681 | 1,00 |

O limiar final é escolhido de forma **conservadora**: entre as regras que sustentam 95%
com pelo menos 20 publicadas, fica-se com a de maior limiar. A leitura aninhada entra
como piso.

## Resultado nas 659

| Decisão | Antigas | Novas | Total |
|---|---|---|---|
| publicar | 55 | 76 | **131** |
| revisar | 304 | 224 | **528** |
| fora | 0 | 0 | 0 |

Nenhuma questão marcada como `fora`: com 8 exemplos rotulados e **nenhum sinal
discriminante** (todos os `fora` têm disciplina dentro do recorte), marcar `fora` seria
chute. `revisar` é a resposta conservadora correta — não afeta a precisão das publicadas.

## Previsão para as 559 (`previsao.txt`)

- **precisão 0,91**, intervalo **0,76–0,99** (posterior Beta-Binomial da regra fixa)
- **cobertura 0,20** (111/559), intervalo 0,18–0,22
  - antigas (259): 35 publicadas = 0,14
  - novas (300): 76 publicadas = 0,25

O intervalo é largo porque 20 publicadas são poucas — é o dado, não uma escolha. A versão
artesanal (0,92 [0,82–0,97]) foi substituída na auditoria por um número rastreável; ver
[`auditoria.md`](auditoria.md), seção 4.

**Ressalva honesta:** o modelo fica *mais* confiante nas 300 novas (pontuação média 0,59
contra 0,49) e por isso publica mais nelas. Pode ser que sejam mais fáceis, pode ser
excesso de confiança fora da distribuição. Sem rótulo, não há como decidir — daí o
intervalo assimétrico.

## O teto estatístico (medido, não estimado)

Com 100 rótulos, provar 95% pelo limite inferior de Wilson exige ~73 acertos em 73
publicadas. A auditoria transformou isso em número: usando a cota exata de
Clopper-Pearson, **não se certifica 95% nem 90% em cobertura alguma** (0 publicações). O
primeiro nível certificável é 15% de erro — 22 publicadas com 21 acertos in-sample — e, no
protocolo aninhado sem vazamento, a certificação honesta fica em **~80%**. O que dá para
fazer — e foi feito — é publicar pouco, escolher o limiar fora do grupo medido e dizer o
intervalo com honestidade. Detalhes em [`auditoria.md`](auditoria.md).

## Estrutura do código

| Módulo | Papel |
|---|---|
| `clean.py` | HTML → texto |
| `temas.py` | árvore + régua de acerto (pai/filho; irmão não conta) |
| `dicionario.py` | expansão de consulta (curado à mão, offline) |
| `recuperacao.py` | TF-IDF palavra/char, BM25, RRF |
| `protocolo.py` | folds agrupados, Wilson, curva, limiar out-of-fold |
| `baseline.py` | Etapa 1 (A0/A1) |
| `reranker.py` | Etapa 3 — testado e **descartado** (empata/perde) |
| `embeddings.py` | Etapa 2 — testado e **descartado** (top-1 pior) |
| `confianca.py` | confiança no nível da questão + regra do pai |
| `decisao.py` | regra seletiva → `publicacao.csv` |
| `previsao.py` | `previsao.txt` (posterior Beta-Binomial + teto certificável) |
| `artefato.py` | carrega a base uma vez, compartilhada por conformal/auditoria |
| `conformal.py` | controle de risco (CRC), precisão certificável, conjuntos + ancestral comum |
| `auditoria.py` | sensibilidade da métrica, aninhado corrigido, regras × logística, manifesto |
