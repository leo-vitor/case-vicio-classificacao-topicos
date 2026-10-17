# Cache de contexto (árvore de temas)

O verificador manda a **árvore inteira** de temas em cada chamada (~9 mil
tokens). O cache de contexto envia esse bloco **uma vez** e o reaproveita nas
demais chamadas, pagando por token em cache a uma fração do token de entrada.

Flag: `CONTEXT_CACHE=1` em `src/verificar_arvore.py`, ou o módulo direto:
`python -m src.contexto_cache`.

## O que está medido e o que não está

- **Plano em tokens (grátis).** `python -m src.contexto_cache --dry-run` não faz
  chamada de API. Saída em 2026-10-17:

  ```
  temas na arvore: 371
  prefixo estatico (instrucoes + arvore): ~9,370 tokens
  sufixo por questao (origem + enunciado): ~367 tokens
  caso                                sem cache    com cache   economia
  verificador (261 publicadas)           2.54M       0.72M       72%
  projecao N=1000                        9.74M       2.72M       72%
  ```

- **Teste real com a API.** O comando `python -m src.contexto_cache --criar` cria
  o cache de verdade e faz **1 chamada**, imprimindo `tokens_in` e
  `cached_content_token_count`. Num teste pequeno anterior, ~98% dos tokens de
  entrada vieram do cache, com a mesma decisão. **Esse 98% não tem log salvo** (a
  saída não foi guardada), então trato como observação, não como medida.

- **Tentativa de reproduzir (2026-10-17).** Rodei `--criar` de novo e a API
  recusou com **402 RESOURCE_EXHAUSTED** (créditos pré-pagos esgotados). O teste
  usa centavos, mas não há crédito no projeto. Portanto: **não reexecutado**, e o
  relatório diz isso.

## Como reproduzir quando houver crédito

```bash
python -m src.contexto_cache --dry-run     # grátis: só o plano em tokens
python -m src.contexto_cache --criar       # usa API: cria o cache e faz 1 chamada
python -m src.contexto_cache --validar --n-validar 3   # compara com os votos guardados
```

Salve a saída de `--criar` (o número `cacheados=`) para virar medida citável.

## Decisão

Não adotar por padrão na entrega: ligar a flag **imediatamente** deixaria a
verificação mais barata, mas os votos de verificação já estavam prontos e o
desconto em R$ depende do contrato, que não foi confirmado. Fica como a alavanca
de custo mais direta para a produção. Registro da decisão:
`docs/decisoes_manuais.md`.
