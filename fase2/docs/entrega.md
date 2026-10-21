# Entrega da Fase 2 — pipeline, resultados e limites

Tudo reproduzível **sem rede e sem LLM** a partir dos anexos. Relatório final (4 páginas) e memo
(1 página) em [`report/relatorio.pdf`](../report/relatorio.pdf); fonte em
[`report/relatorio.tex`](../report/relatorio.tex). Comandos:

```bash
cd fase2
.venv/bin/python -m src.baseline      # Etapa 1: baseline lexical
.venv/bin/python -m src.confianca     # Etapa 3: confiança no nível da questão
.venv/bin/python -m src.pisos         # Etapa 2: pisos gratuitos + ablação por campo
.venv/bin/python -m src.cascata       # Etapa 2: ramo em 2 estágios + disciplina
.venv/bin/python -m src.decisao       # Etapas 3/4: decisão seletiva -> publicacao.csv
.venv/bin/python -m src.previsao      # Etapa 5: previsao.txt
```

O único insumo novo em relação à Fase 1 é `enriquecimento_v01.jsonl` (351 temas, sha256
`d906aa5a5619`), lido do disco. Nenhum passo chama modelo: o artefato foi gerado uma vez,
offline, e está versionado com a procedência em
[`procedencia_enriquecimento.md`](procedencia_enriquecimento.md).

## O que a investigação mostrou

### 0. O enriquecimento venceu o critério — e só ele

Antes de gastar token, a pergunta era se hierarquia e dicionário já resolviam o ramo.
Não resolvem: `+filhos`, `+dicionario_tema` e a combinação ficam em **0,641** de `ramo@1`,
o mesmo que o `base`. Com o artefato, **0,728** (`+0,087`), e a precisão a 20% de cobertura
sobe de 0,67 para 0,72. A ablação mostra que nenhum campo sozinho basta (sinônimos isolados
ficam *abaixo* da base); o ganho vem da combinação sinônimos + institutos + texto. Detalhes
em [`etapa2_pisos.md`](etapa2_pisos.md).

### 1. A régua do case premia o nó pai

Se o top-1 é um subtema (nível 2), publicar o **tema pai** (nível 1) nunca piora: a régua
aceita o pai, e o pai cobre também os irmãos. Medido nos 100, com o texto enriquecido:

| Recuperador | publicando o top-1 | promovendo nível 2 → pai | ganho | perda |
|---|---|---|---|---|
| rrf_all (campeão) | 61 | 67 | +6 | 0 |

Zero perdas. É a regra mais barata do case — e a razão de o sistema responder sempre no
nível do ramo.

### 2. O melhor recuperador é o TF-IDF de caracteres (mas o RRF decide melhor)

`tfidf_char` tem o melhor recall hierárquico no top-10 (0,91), porque os títulos da
árvore são curtos e o domínio é morfológico. Já para **top-1**, `rrf_all` (TF-IDF + BM25)
é o mais preciso. Curiosidade medida na Etapa 2: o enriquecimento ajuda o `tfidf_char`
mais do que qualquer outro (`ramo@1` 0,554 → 0,717), porque acrescenta variações
morfológicas que o n-grama de caractere captura. Mesmo assim o campeão não muda: trocar
`rrf_all` por `char` ganharia +0,011 e custaria uma mudança de arquitetura.

### 3. Reranker de candidatos **não** ajudou — e isso está documentado

Rodei um reranker logístico sobre 16 features de candidato (posição, margem, relação
com o top-1, gêmeo, lei citada, prior). Resultado: melhor caso empata com a regra v0 e,
em geral, perde. **Decisão: não entra na entrega** (regra de parada: sem ganho, sem
complexidade).

### 4. Embeddings densos também não — por ora

`intfloat/multilingual-e5-large` (local, MPS, vetores versionados): hier@10 = 0,79
isolado e 0,92 no híbrido com o char, mas **top-1 pior**. Como a decisão vive do top-1,
embeddings ficam de fora. `k`-NN entre questões (usando os rótulos) também foi pior.

### 5. O que funcionou: **consenso entre recuperadores**

O sinal mais forte não é a similaridade, é a **concordância**:

| Consenso | n | precisão (régua do case) |
|---|---|---|
| 0,25 | 100 | 0,670 |
| 0,50 | 96 | 0,688 |
| 0,75 | 82 | 0,732 |
| **1,00** | **51** | **0,804** |

E o consenso pegou parte dos casos fora da taxonomia: 4 dos 8 `fora` ficam com
consenso ≤ 0,75 e são barrados automaticamente (antes do enriquecimento eram 6 de 8 — o
enriquecimento deixou 4 `fora` parecidos com temas reais, o que é um custo a registrar).

### 6. Ramo em dois estágios **não** melhora a decisão

Agregar os filhos por máximo é a mesma coisa que promover o top-1; somar os três melhores
piora (`−0,087`) e tirar a média piora muito (`−0,283`). A disciplina de origem como prior
dá +0,022, dentro do ruído (validação aninhada: 0,750 contra 0,728), e não foi adotada.
Publicar o subtema em vez do ramo nunca salva um ramo errado (0 casos em 92). Detalhes em
[`etapa5_cascata.md`](etapa5_cascata.md).

## Ponto de operação escolhido

**Publicar se consenso ≥ 0,75 E confiança ≥ 0,896173** (confiança = regressão logística
sobre 14 features de topo de ranking). Caso contrário, `revisar`.

| Leitura | Publicadas | Acertos | Precisão | IC 95% (Wilson) | Cobertura |
|---|---|---|---|---|---|
| In-sample (regra fixa) | 20 | 19 | 0,950 | 0,764–0,991 | 0,20 |
| Aninhada (limiar fora do grupo) | 20 | 18 | 0,900 | 0,699–0,972 | 0,20 |
| Publicando tudo | 100 | 67 | 0,670 | 0,573–0,755 | 1,00 |

O limiar final é escolhido de forma **conservadora**: entre as regras que sustentam 95%
com pelo menos 20 publicadas, fica-se com a de maior limiar. A leitura aninhada entra
como piso. O consenso mínimo caiu de 1,00 para 0,75 porque, com o texto melhor, três
recuperadores concordando já é evidência suficiente para sustentar 95% com mais cobertura
— e é isso que a escolha fora da dobra indica.

## Resultado nas 659

| Decisão | Antigas | Novas | Total |
|---|---|---|---|
| publicar | 70 | 60 | **130** |
| revisar | 289 | 240 | **529** |
| fora | 0 | 0 | 0 |

Nenhuma questão marcada como `fora`: com 8 exemplos rotulados e **nenhum sinal
discriminante**, marcar `fora` seria chute. `revisar` é a resposta conservadora correta —
não afeta a precisão das publicadas.

Por ramo: Penal 69, Processo Penal 44, Criminologia 13, Legislação Especial 4. As quatro
publicações em Legislação Especial são novas (antes o consenso nunca fechava nesse
estrato); é o efeito mais visível do enriquecimento fora do par Penal/Processo Penal.

## Previsão para as 559 (`previsao.txt`)

- **precisão 0,91**, intervalo **0,76–0,99** (posterior Beta-Binomial da regra fixa)
- **cobertura 0,19** (108/559), intervalo 0,17–0,21
  - antigas (259): 48 publicadas = 0,19
  - novas (300): 60 publicadas = 0,20

O intervalo é largo porque 20 publicadas são poucas — é o dado, não uma escolha.

**Ressalva honesta:** antes do enriquecimento o modelo era bem mais confiante nas 300
novas (0,59 contra 0,49 de pontuação média) e publicava 0,25 nelas contra 0,14 nas antigas.
Agora a diferença caiu para 0,05 e a cobertura é 0,20 contra 0,19. A assimetria não
desapareceu, mas deixou de ser o ponto mais frágil da previsão.

## O teto estatístico (medido, não estimado)

Com 100 rótulos, provar 95% pelo limite inferior de Wilson exige ~73 acertos em 73
publicadas. A auditoria transformou isso em número: usando a cota exata de
Clopper-Pearson, **não se certifica 95% nem 90% em cobertura alguma** (0 publicações). O
primeiro nível certificável é 15% de erro — 33 publicadas com 31 acertos in-sample — e, no
protocolo aninhado sem vazamento, a certificação honesta fica em **~85%** (41 publicadas,
35 acertos a 20% de erro). O que dá para fazer — e foi feito — é publicar pouco, escolher o
limiar fora do grupo medido e dizer o intervalo com honestidade. Detalhes em
[`auditoria.md`](auditoria.md).

## Estabilidade: o custo do enriquecimento

O ganho de `ramo@1` não é um ajuste fino: 268 dos 659 temas mudam de nome (40,7%) e 177
decisões mudam (26,9%); das ~130 publicadas, apenas 42 estavam publicadas antes. A
precisão e a cobertura melhoram, mas o sistema está operando numa faixa de margens
pequenas — pequenas mudanças de vocabulário movem questões através do limiar. Isso não
invalida o 95% medido e impede tratá-lo como garantia. Números em
[`etapa5_cascata.md`](etapa5_cascata.md).

## Estrutura do código

| Módulo | Papel |
|---|---|
| `clean.py` | HTML → texto |
| `temas.py` | árvore + régua de acerto (pai/filho; irmão não conta) |
| `dicionario.py` | expansão de consulta (curado à mão, offline) |
| `enriquecimento.py` | lê o artefato e monta o `texto_tema` enriquecido |
| `recuperacao.py` | TF-IDF palavra/char, BM25, RRF |
| `protocolo.py` | folds agrupados, Wilson, curva, limiar out-of-fold |
| `baseline.py` | Etapa 1 (A0/A1) |
| `pisos.py` | pisos gratuitos + ablação por campo (Etapa 2) |
| `cascata.py` | ramo em 2 estágios, agregação e prior de disciplina |
| `reranker.py` | testado e **descartado** (empata/perde) |
| `embeddings.py` | testado e **descartado** (top-1 pior) |
| `confianca.py` | confiança no nível da questão + regra do pai |
| `decisao.py` | regra seletiva → `publicacao.csv` |
| `previsao.py` | `previsao.txt` (posterior Beta-Binomial + teto certificável) |
| `artefato.py` | carrega a base uma vez, compartilhada por conformal/auditoria |
| `conformal.py` | controle de risco (CRC), precisão certificável, conjuntos + ancestral comum |
| `auditoria.py` | sensibilidade da métrica, aninhado corrigido, regras × logística, manifesto |
| `validador_enriquecimento.py` | contrato do artefato (offline, sem dependências) |
