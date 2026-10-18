# Metodologia de avaliação (precisão, cobertura e verificação)

Documento de apoio ao `previsao.txt` e ao relatório. Todos os números abaixo
saem de scripts **offline** (sem chamadas de API) e podem ser reproduzidos.

## 1. O que é medido

- **Concordância** (o que chamamos de "precisão observada"): só sobre as questões
  **publicadas**. Um acerto é publicar no tema correto, no pai ou em um filho
  direto (régua do case). Irmãos = erro.
- **Cobertura**: fração das 359 publicadas. É a contagem determinística do
  pipeline (não vem de amostragem).
- As questões rotuladas que estão em `revisar`/`fora` **não** entram no
  denominador; elas viram diagnóstico de cobertura
  (`outputs/cobertura_diagnostico.csv`).

Ressalva central: os rótulos vêm de outro LLM (**DeepSeek**), então a métrica é
**concordância entre modelos**, não precisão contra especialistas. Ver
`docs/transparencia_rotulos.md`.

## 2. Pipeline e amostra

Pipeline atual: `clean → candidates (TF-IDF + pais/filhos) → judge (gemini-3.6-flash
e gemini-3.1-flash-lite, 4 votos) → expandir_fora → fallback_arvore (árvore
inteira) → verificar_arvore (5º voto) → decide → validate`.

- **Grupo A**: publicadas só depois do fallback (maior risco). Censo: 15/15.
- **Grupo B**: demais publicadas; amostra aleatória (seed fixa).
- Amostra total: **93 rótulos**, dos quais **68 publicados na base** e **60
  publicados após o verificador**.

## 3. Números desta execução

**Base** (antes do verificador): **261 publicadas** (72,7%). Concordância
observada **0,838** (57/68); estrita 0,480; pessimista 0,765; recall dos
candidatos 82/93.

**Entrega atual** (após o verificador): **222 publicadas** (61,8%). Concordância
observada **0,90** (54/60), Wilson [0,80; 0,95].

| Métrica | Valor |
|---|---|
| Publicadas (cobertura) | 222/359 = 0,618 |
| Rotuladas e publicadas | 60 |
| Concordância observada | 54/60 = 0,90 |
| Wilson 95% | [0,80; 0,95] |
| Verificador: concordâncias / discordâncias | 225 / 36 |
| Rebaixadas (inclui 3 por re-agregação) | 39 |
| Erros pegos pelo verificador | 5 de 11 |
| Falsos vetos (certas rebaixadas) | 3 |

Adjudicação dos 6 desacordos reais (`docs/adjudicacao_erros.csv`): 1 favorece o
rótulo (`Q0120`), 1 favorece o modelo (`Q0238`) e 4 são ambíguos. Como a
adjudicação é de **não especialista**, ela é sensibilidade, não medição:
- só "modelo certo": 0,92 (55/60);
- tratando ambíguos também a favor: 0,98 (59/60) — teto otimista.

## 4. Por que um único rotulador não é gabarito

`python -m src.experimentos.audit votos` trata os 4 votos do juiz como anotadores de um modelo
latente *one-coin* e estima a confiabilidade de cada um **sem gabarito**:

| Anotador | Acurácia estimada |
|---|---|
| v0 (flash) | 0,778 |
| v1 (flash) | 0,770 |
| v2 (flash-lite) | 0,976 |
| v3 (flash-lite) | 0,995 |

Cuidado: os votos são correlacionados e restritos aos candidatos. Serve como
sinal auxiliar, não como verdade.

## 5. Verificador (5º voto, árvore inteira)

Como os erros eram **unânimes** (4/4) por falha de recuperação, a concordância não
os separa. O verificador dá ao `flash-lite` a árvore inteira e usa o voto extra
para rebaixar discordâncias. Auditoria completa e IDs: `docs/auditoria_verificador.md`.

## 6. Recuperação: o que foi testado e por que ficou como recomendação

Experimento offline (`python -m src.experimentos.recall_recuperacao`), contra os 93 rótulos,
medindo **recall 1-hop** (tema, pai ou filho presente na lista):

| Configuração (k=10) | recall 1-hop | candidatos |
|---|---|---|
| TF-IDF + pais/filhos (atual) | 0,667 | 14 |
| **TF-IDF + irmãos dos top-k** | **0,882** | 80 |
| Denso local (e5-large) + irmãos | 0,87 | — |
| RRF (TF-IDF + denso e5-large) + irmãos | 0,88 | — |

- A expansão por **irmãos** é a alavanca grátis: faz o tema correto entrar na
  lista. A expansão atual (pai/filho) é quase inerte para recall.
- BM25 é pior que TF-IDF; a fusão RRF com denso só fica competitiva com um
  modelo **grande** (`e5-large`, ~2,2 GB) e, mesmo assim, **não supera** o
  TF-IDF + irmãos.
- **Legislação Especial** continua o buraco em todos os métodos (~0,4).

Por que **não** entrou na entrega: mexer em `candidatos.json` muda o prompt e
**invalida o cache** do juiz (re-julgamento pago), e o ganho de recall não foi
medido fim-a-fim. Fica como recomendação de produção.

Detalhes: `outputs/experimentos/recall_resumo.md`.

## 7. Limitações (vão para o `previsao.txt`)

- Amostra pequena e rotulada com assistência de IA → a métrica é **concordância**,
  não acerto contra especialistas.
- Sem gabarito humano, não há garantia conformal; falamos em "avaliação
  preliminar", não em "95% garantido".
- A regra do verificador foi avaliada na mesma amostra onde nasceu.
- O verificador usa a mesma família do juiz; erros podem ser correlacionados.
- Os temas **gêmeos** (título duplicado) permanecem ambíguos e foram mantidos em
  `revisar`; a convenção da organização não foi confirmada.
- O uso/custo da verificação não foi registrado (`outputs/uso.json`).

## 8. Referências

- Geifman & El-Yaniv (2017), *Selective Classification for Deep Neural Networks*.
- Angelopoulos et al. (2024), *Conformal Risk Control*.
- Dawid & Skene (1979); Raykar et al. (2010) — rótulos ruidosos / classes latentes.
- Silveira et al. (2023) — Legal-BERTimbau / LegalBert-pt (proposta de produção).
- Cormack et al. (2009) — Reciprocal Rank Fusion (testada em `src/experimentos/recall_recuperacao.py`).
