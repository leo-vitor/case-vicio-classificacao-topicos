# Decisões metodológicas — Fase 2

Registro do que foi decidido, por quê, e do que **não** entra. Escrito para ser lido
junto com o relatório.

## 1. Sem LLM na decisão

O enunciado veda chamar modelo de linguagem para classificar. Na prática, isso elimina
juiz-LLM em tempo de execução. LLM pode aparecer **offline** (limpeza, dicionário,
embeddings), desde que o resultado seja versionado e a execução final rode sem rede.

**Consequência de desenho:** a decisão é recuperação + modelo supervisionado pequeno.

## 2. Só os 100 rótulos de especialista

A Fase 1 tinha rótulos assistidos por IA. Usá-los aqui mediria "concordância com IA",
não acurácia. A Fase 2 usa exclusivamente `folha_verdade.csv` (100 questões, todas
Q0001–Q0359). As 300 novas **não têm rótulo** — entram só na previsão.

## 3. Recuperação + decisão seletiva, não classificador plano

61 temas centrais distintos em 100 exemplos, 42 deles com 1 exemplo. Não há dados para
um classificador de 371 classes nem para um transformer. O desenho é:

```
recuperar candidatos → extrair features → reranker pequeno → score → regra seletiva
```

## 4. A unidade de inferência é a questão, não o par

100 questões × ~50 candidatos = ~5.000 pares, mas **correlacionados**. A validação
separa questões inteiras (folds agrupados por near-duplicata) e nunca distribui
candidatos da mesma questão entre treino e teste. A quantidade de pares **não** é
argumento de que há muitos dados.

## 5. O limiar é escolhido fora da dobra

O único parâmetro "aprendido" da regra v0 é o limiar. Escolhê-lo no mesmo conjunto que
mede a precisão infla o número. A escolha é nested (treino da dobra) e a medição é no
teste. A curva completa é reportada à parte, porque para um limiar *fixo* ela não tem
viés.

## 6. Wilson, não calibração mágica

Calibração (Platt/isotônica) ajusta score → probabilidade; **não cria evidência**.
Com 100 exemplos, isotônica é instável. O critério de decisão usa o **limite inferior
de Wilson** da precisão, que é o que se pode afirmar com 95% de confiança.

Referência dura: para o limite inferior bater 95% são necessários ~**73 acertos em 73
publicadas**. A meta é publicar pouco e bem.

## 7. `fora` é conservador

Baixa similaridade e margem pequena indicam **incerteza**, não "fora da taxonomia".
Com 8 exemplos de `fora`, não se treina classificador. A regra: só marcar `fora` com
evidência forte (disciplina fora do recorte + score baixo); na dúvida, `revisar`.

## 8. Régua do case, não multilabel

A saída é **um** tema central; `extras_ids` são sugestões auxiliares. O acerto segue o
LEIA-ME: central, extra, pai ou filho direto. Irmão conta como erro. O campo
`confianca` é a chance do **tema central** estar certo.

## 9. Embeddings locais e versionados

Se embeddings entrarem (Etapa 2), serão **locais** (`bge-m3` / `multilingual-e5-large`),
com modelo, revisão, dimensão e hash dos textos registrados. Nada de API externa na
execução final.

## 10. Repositório único, em fases

Fase 1 congelada na tag `v1-fase1`; Fase 2 em `fase2/`, autocontida. Um repositório
conta a evolução (entrega → crítica → melhoria) melhor do que dois projetos soltos.
A Fase 2 copia os módulos reaproveitáveis em vez de importar de `fase1/`, para poder
rodar sozinha.

## Regra de parada

Cada etapa só avança se superar a anterior **fora da dobra**, com ganho pré-definido.
Sem ganho, fica a versão mais simples. O erro clássico de um case é acumular
complexidade sem evidência.

## O que fica de fora (por ora)

- Classificador plano de 371 classes.
- Fine-tuning de encoder (com 100 rótulos, não se justifica).
- Conformal prediction e learning-to-rank: secundários, só depois de uma curva
  precisão × cobertura competitiva com regras simples.
- ECE como métrica principal (ruidoso com 100 pontos).
