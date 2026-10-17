# Experimento de recuperação (offline, custo zero de API)

Mede se o tema correto (ou o pai) entra no conjunto de candidatos, contra os **93 rótulos**.
Régua do case: mesmo tema, pai ou filho direto (irmão não conta).

Script: `python -m src.recall_recuperacao` → `outputs/experimentos/recall_recuperacao.csv`

## Resultado principal (k=10, TF-IDF)

| Expansão | recall exato | recall 1-hop | nº médio de candidatos |
|---|---|---|---|
| top (só os 10) | 0,645 | 0,645 | 10 |
| +pai | 0,645 | 0,667 | 12 |
| +filho (lógica atual) | 0,645 | 0,667 | 14 |
| **+irmãos dos top-3** | 0,720 | **0,860** | 52 |
| +irmãos de todos os top-10 | 0,753 | 0,882 | 80 |

- **A expansão atual (pai/filho) é quase inerte para recall** (0,645 → 0,667).
- **O que move o recall é a expansão por irmãos** (→ 0,86), que é justamente o que a
  proposta "expansão contextual" acrescenta. Custo: a lista ~4x maior.
- Com irmãos, Penal e Processo Penal chegam a **recall 1-hop de 1,00** na amostra.
- **Legislação Especial continua o buraco: 7/19 = 0,37** (era 2/19 = 0,11 sem irmãos).
- Restam 13 questões fora (`recall_faltas.csv`), concentradas em Legislação Especial.

## Recuperadores (k=10, +filho)

| Recuperador | recall 1-hop |
|---|---|
| TF-IDF (atual) | **0,667** |
| BM25 | 0,548 |
| RRF (TF-IDF + BM25) | 0,613 |
| Denso local (multilingual-e5-small) | 0,591 |
| RRF (TF-IDF + denso) | 0,677 |
| RRF (TF-IDF + BM25 + denso) | 0,699 |

BM25 é pior que TF-IDF, o denso local também, e nenhuma fusão RRF bate
**TF-IDF + irmãos** (1-hop 0,882 @ k=10 e 0,946 @ k=30). O denso melhora a RRF em
relação ao BM25, mas ainda fica abaixo do TF-IDF só com a expansão por irmãos.
O `candidatos.json` atual mostra 1-hop 0,882, mas está inflado pelo fallback
(árvore inteira em parte das questões).

### Leitura

- O gargalo **não** é resolvido por um embedder denso pequeno neste corpus: os
  "documentos" de tema são curtos (caminho + título) e o jargão jurídico favorece
  a correspondência lexical.
- A alavanca grátis e efetiva é **estrutural**: expandir candidatos com os irmãos
  dos top-k faz o tema correto entrar na lista (0,667 → 0,882).
- Legislação Especial segue como exceção (0,47 mesmo com irmãos).

### Efeito do tamanho do embedder (recall 1-hop @ k=10, +irmãos)

| Ranker | e5-small | e5-base | e5-large |
|---|---|---|---|
| denso | 0,61 | 0,81 | 0,87 |
| RRF (TF-IDF + denso) | 0,81 | 0,85 | **0,88** |
| RRF (TF-IDF + BM25 + denso) | 0,83 | 0,84 | 0,86 |
| **TF-IDF + irmãos (grátis)** | **0,88** | **0,88** | **0,88** |

Com o `e5-large` (~2,2 GB, ~560M parâmetros) a RRF densa **empata** com o TF-IDF
+ irmãos em k=10 (0,88) e passa à frente só em k=15 (0,92 vs 0,89). Ou seja: só um
modelo grande torna o denso competitivo, e ele **não supera** a opção lexical +
estrutural, que é instantânea e sem download. Legislação Especial continua o buraco
em todos os métodos (denso-large + irmãos: 8/19 = 0,42).

Conclusão prática: a recomendação de produção é a **expansão estrutural por irmãos**;
o denso só se justifica se houver GPU e um modelo ajustado ao domínio.

## Ressalvas

- Recall é condição necessária, não prova de ganho fim-a-fim: uma lista 4x maior
  pode confundir o juiz. Não foi medido o efeito na precisão publicada.
- Adotar isso no pipeline **invalida o cache do juiz** (a chave depende do prompt,
  que inclui a lista de candidatos) → re-julgamento pago. Fica como recomendação
  de produção (seção c do relatório), não no `publicacao.csv` entregue.
