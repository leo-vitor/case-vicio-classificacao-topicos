# Entrega da Fase 2 — pipeline, resultados e limites

Tudo reproduzível **sem rede e sem LLM** a partir dos anexos. Relatório final (4 páginas) e memo
(1 página) em [`report/relatorio.pdf`](../report/relatorio.pdf); fonte em
[`report/relatorio.tex`](../report/relatorio.tex). Comandos:

```bash
cd fase2
./scripts/regenerar.sh   # pipeline completo: publicacao.csv + previsao.txt + artefatos
```

O script roda `clean → baseline → confianca → decisao → conformal → auditoria → previsao`
(e, no fim, `diagnostico` e `regra_final`) e para no primeiro erro. Leva ~60 s em um núcleo,
sem rede. Para rodar um módulo isolado: `.venv/bin/python -m src.<modulo>`.

O único insumo novo em relação à Fase 1 é `enriquecimento_v01.jsonl` (351 temas, sha256
`7bbda02e4c65`), lido do disco. Nenhum passo chama modelo: o artefato foi gerado uma vez,
offline, e está versionado com a procedência em
[`procedencia_enriquecimento.md`](procedencia_enriquecimento.md). A árvore é a do case
(`data/temas.csv`) com os ajustes de `src/taxonomia.py` (v02), que só corrigem a hierarquia
de 5148 e 5156 sob 5155 — ver [`decisoes.md`](../../docs/decisoes.md), seção 12.

## O que a investigação mostrou

### 0. O enriquecimento venceu o critério — e só ele

Antes de gastar token, a pergunta era se hierarquia e dicionário já resolviam o ramo.
Não resolvem: `+filhos`, `+dicionario_tema` e a combinação ficam em **0,641** de `ramo@1`,
o mesmo que o `base`. Com o artefato, **0,739** (`+0,109`), e a precisão a 20% de cobertura
sobe de 0,67 para 0,72. A ablação mostra que nenhum campo sozinho basta (sinônimos isolados
ficam *abaixo* da base) nem é individualmente necessário (toda remoção fica no ruído); o
ganho vem da combinação, e somar o dicionário ao texto enriquecido atrapalha (−0,054).
Detalhes em [`etapa2_pisos.md`](etapa2_pisos.md).

### 1. A régua do case premia o nó pai

Se o top-1 é um subtema (nível 2), publicar o **tema pai** (nível 1) nunca piora: a régua
aceita o pai, e o pai cobre também os irmãos. Medido nos 100, com o texto enriquecido:

| Recuperador | publicando o top-1 | promovendo nível 2 → pai | ganho | perda |
|---|---|---|---|---|
| rrf_all (campeão) | 62 | 68 | +6 | 0 |

Zero perdas. É a regra mais barata do case — e a razão de o sistema responder sempre no
nível do ramo.

### 2. O melhor recuperador no top-10 é o TF-IDF de caracteres (mas o RRF decide melhor no top-1)

`tfidf_char` tem o melhor recall hierárquico no top-10 (0,91), porque os títulos da
árvore são curtos e o domínio é morfológico. Já para **top-1**, `rrf_all` (TF-IDF + BM25)
é o mais preciso: 0,739 contra 0,717 do `char` com o mesmo artefato. O enriquecimento
ajuda o `char` mais do que qualquer outro (0,554 → 0,717), porque acrescenta variações
morfológicas que o n-grama de caractere captura — mas não o bastante para trocar o
campeão. Trocar custaria uma mudança de arquitetura e **perderia** 0,022.

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
| 0,25 | 100 | 0,680 |
| 0,50 | 96 | 0,698 |
| 0,75 | 83 | 0,723 |
| **1,00** | **51** | **0,804** |

E o consenso pegou parte dos casos fora da taxonomia: 4 dos 8 `fora` ficam com
consenso ≤ 0,75 e são barrados automaticamente (antes do enriquecimento eram 6 de 8 — o
enriquecimento deixou 4 `fora` parecidos com temas reais, o que é um custo a registrar).

### 6. Ramo em dois estágios **não** melhora a decisão

Agregar os filhos por máximo é a mesma coisa que promover o top-1; somar os três melhores
piora (`−0,087`) e tirar a média piora muito (`−0,271`). A disciplina de origem como prior
dá +0,033 (validação aninhada: 0,761 contra 0,739), com IC do delta tocando o zero, e
**não foi adotada**: é um parâmetro a mais com efeito dentro do ruído. Publicar o subtema
em vez do ramo nunca salva um ramo errado (0 casos em 92). Detalhes em
[`etapa5_cascata.md`](etapa5_cascata.md).

## Ponto de operação escolhido

**Publicar se consenso ≥ 0,75 E confiança ≥ 0,895946** (confiança = regressão logística
sobre 13 features de topo de ranking). Caso contrário, `revisar`.

| Leitura | Publicadas | Acertos | Precisão | IC 95% (Wilson) | Cobertura |
|---|---|---|---|---|---|
| In-sample (regra fixa) | 20 | 19 | 0,950 | 0,764–0,991 | 0,20 |
| Aninhada corrigida (limiar fora do grupo) | 17 | 13 | 0,765 | 0,527–0,904 | 0,17 |
| Publicando tudo | 100 | 68 | 0,680 | 0,582–0,763 | 1,00 |

O limiar final é escolhido de forma **conservadora**: entre as regras que sustentam 95%
com pelo menos 20 publicadas, fica-se com a de maior limiar. A leitura aninhada entra
como piso — e ela é o número honesto sobre o que a regra entrega fora da amostra que a
escolheu. O consenso mínimo caiu de 1,00 para 0,75 porque, com o texto melhor, três
recuperadores concordando já é evidência suficiente para sustentar 95% com mais cobertura
— e é isso que a escolha fora da dobra indica.

A curva precisão × cobertura é plana entre 17% e 37% de cobertura (0,95 a 0,97): o
conservadorismo custa 17 publicações sem ganho mensurável de precisão *nesta amostra*, mas a
fronteira in-sample não corrige a seleção — o CRC a 10% dá 0,816 e o aninhado 0,765. Mover o
limiar agora seria escolhê-lo no conjunto que mede. Detalhes em
[`regra_final.md`](regra_final.md).

### Correção do `lei_match`

A feature `lei_match` valia 1 em 1 das 100 questões e em 25 das 659, e dominava o logit
(z ≈ 9,95; coeficiente +2,98). É um singleton: a folha não estima o peso dele. Removi —
correção, não tuning. O efeito: τ 0,887009 → 0,895946; 118 → **115** publicadas (61 antigas
+ 54 novas); aninhado 13/15 = 0,867 → **13/17 = 0,765**; e 5 das 6 publicações em
Legislação Especial sumiram. Q0035, publicada com `p_all` 0,96, volta a 0,59 e vai para
revisão. O número de 6 em Legislação Especial não sobrevive à correção; o de 1 (0 na folha)
é o que fica.

## Diagnóstico: busca ou decisão?

Das 92 válidas: 20 publicadas certas, 1 errada, **48 revisadas com o top-1 já no ramo certo**
(18 passariam no limiar mais baixo do platô; 30 precisam de modelo), 18 com o ramo certo entre
o 2º e o 10º e 5 fora do top-10. O top-10 cobre 94,6%, mas o gargalo é misto: 30 de confiança,
18 de ranking e 5 de recall. Detalhes em [`diagnostico.md`](diagnostico.md). Os recuperadores
empatam no top-1, exceto o `tfidf`, que é pior; em
[`etapa3_recuperadores.md`](etapa3_recuperadores.md).

## Resultado nas 659

| Decisão | Antigas | Novas | Total |
|---|---|---|---|
| publicar | 61 | 54 | **115** |
| revisar | 298 | 246 | **544** |
| fora | 0 | 0 | 0 |

Nenhuma questão marcada como `fora`: com 8 exemplos rotulados e **nenhum sinal
discriminante**, marcar `fora` seria chute. `revisar` é a resposta conservadora correta —
não afeta a precisão das publicadas.

Por ramo: Penal 67, Processo Penal 41, Legislação Especial 1, Criminologia 6. A remoção do
`lei_match` custou 5 das 6 publicações em Legislação Especial (Terrorismo, Organizações
Criminosas, Estatuto do Desarmamento, Abuso de Autoridade, Tortura); na folha o estrato
voltou a 0 (6 revisadas com top-1 certo). O enriquecimento continua pondo o ramo certo no
top-1, mas a publicação de Legislação Especial estava apoiada na feature singleton.

## Previsão para as 559 (`previsao.txt`)

- **precisão 0,91**, intervalo **0,76–0,99** (posterior Beta-Binomial da regra fixa)
- **cobertura 0,17** (94/559), intervalo 0,15–0,19
  - antigas (259): 40 publicadas = 0,15
  - novas (300): 54 publicadas = 0,18

O intervalo é largo porque 20 publicadas são poucas — é o dado, não uma escolha.

**Ressalva honesta:** o modelo é um pouco mais confiante nas 300 novas (0,584 contra
0,530 de pontuação média). A cobertura é 0,18 contra 0,15, então a assimetria não é o ponto
frágil da previsão; o ponto frágil é o tamanho da amostra rotulada.

## O teto estatístico (medido, não estimado)

Com 100 rótulos, provar 95% pelo limite inferior de Wilson exige ~73 acertos em 73
publicadas. A auditoria transformou isso em número: usando a cota exata de
Clopper-Pearson, **não se certifica 95% nem 90% em cobertura alguma** (0 publicações). O
primeiro nível certificável é 12% de erro — 32 publicadas com 31 acertos in-sample — e, no
protocolo aninhado sem vazamento, a certificação honesta fica em **0,80** (30 publicadas,
24 acertos a 20% de erro). O que dá para fazer — e foi feito — é publicar pouco, escolher
o limiar fora do grupo medido e dizer o intervalo com honestidade. Detalhes em
[`auditoria.md`](auditoria.md).

## Estabilidade: o custo do enriquecimento

O ganho de `ramo@1` não é um ajuste fino: 266 dos 659 temas mudam de ramo (40,4%) quando
se troca o texto do tema pelo enriquecido. O sistema está operando numa faixa de margens
pequenas — mudanças de vocabulário movem questões através do limiar. Isso não invalida o
0,95 medido e impede tratá-lo como garantia.

A correção de taxonomia (v02) deu a medida mais direta desse problema: mexer em **3 nós**
(5148 e 5156 reparentados, 5156 reescrito) mudou **18 decisões** em 659 (na versão medida, antes da correção do
`lei_match`) e **nenhum tema previsto** entre as 15 que deixaram de ser publicadas. Ou seja, a instabilidade mora na
camada de decisão, não na busca — exatamente onde o próximo ciclo vai trabalhar. Números
em [`etapa5_cascata.md`](etapa5_cascata.md).

## Estrutura do código

| Módulo | Papel |
|---|---|
| `clean.py` | HTML → texto |
| `temas.py` | árvore + régua de acerto (pai/filho; irmão não conta) |
| `taxonomia.py` | ajustes v02 da árvore (5148/5156 sob 5155), aplicados no carregamento |
| `dicionario.py` | expansão de consulta (curado à mão, offline) |
| `enriquecimento.py` | lê o artefato e monta o `texto_tema` enriquecido |
| `recuperacao.py` | TF-IDF palavra/char, BM25, RRF, desempate estável do top-1 |
| `protocolo.py` | folds agrupados, Wilson, curva, limiar out-of-fold |
| `baseline.py` | Etapa 1 (A0/A1) |
| `pisos.py` | pisos gratuitos + ablação por campo (Etapa 2) |
| `cascata.py` | ramo em 2 estágios, agregação e prior de disciplina |
| `reranker.py` | testado e **descartado** (empata/perde) |
| `embeddings.py` | testado e **descartado** (top-1 pior) |
| `confianca.py` | confiança no nível da questão + regra do pai |
| `decisao.py` | regra seletiva → `publicacao.csv` |
| `diagnostico.py` | recuperação × decisão (categorias exclusivas, denominadores explícitos) |
| `recuperadores.py` | recall@1/5/10 pareado por recuperador e disciplina |
| `regra_final.py` | curva precisão × cobertura, fronteira certificável e robustez |
| `previsao.py` | `previsao.txt` (posterior Beta-Binomial + teto certificável) |
| `artefato.py` | carrega a base uma vez, compartilhada por conformal/auditoria |
| `conformal.py` | controle de risco (CRC), precisão certificável, conjuntos + ancestral comum |
| `auditoria.py` | sensibilidade da métrica, aninhado corrigido, regras × logística, manifesto |
| `validador_enriquecimento.py` | contrato do artefato (offline, sem dependências) |
