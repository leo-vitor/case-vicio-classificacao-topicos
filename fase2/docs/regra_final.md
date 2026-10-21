# Experimento 5 — regra final: curva precisão × cobertura e robustez

Pergunta: a regra entregue está num ponto razoável da curva, ou foi um pico de sorte? E
quanto ela se move com o ruído de 100 rótulos?

Reproduz com `python -m src.regra_final` (~10 s). Artefato: `artefatos/regra_final.json`.
Usa `p_oof` (probabilidade fora da dobra) e o consenso do top-1 — as grandezas que
escolheram a regra. A cota de Clopper-Pearson é **unilateral**, a mesma de
`src/conformal.py`, para que as duas fronteiras sejam comparáveis.

## Ponto entregue

`consenso ≥ 0,75` e `p ≥ 0,895946` → **19/20 = 0,950**, Wilson [0,764; 0,991], cobertura
0,20 na folha. Nas 659: **115 publicar / 544 revisar**.

Cota superior do erro (Clopper-Pearson): **0,159 a 15%** e **0,142 a 20%**. Ou seja, o ponto
entregue só se certifica a 20% de erro — a 15% ele não passa.

## Curva (consenso fixo em 0,75)

Melhor precisão em cada nível de cobertura:

| cobertura | τ | publicadas | acertos | precisão | Wilson inf. |
|---|---|---|---|---|---|
| ≥ 0,05 | 0,979 | 5 | 5 | 1,000 | 0,566 |
| ≥ 0,10 | 0,743 | 37 | 36 | **0,973** | 0,862 |
| ≥ 0,40 | 0,704 | 40 | 38 | 0,950 | 0,835 |
| ≥ 0,50 | 0,526 | 53 | 46 | 0,868 | 0,752 |
| **entregue** | **0,896** | **20** | **19** | **0,950** | **0,764** |

**A curva é plana entre 20% e 37% de cobertura** (0,950 → 0,973) e só cai depois de 40%.
O critério "mais conservador entre os que sustentam 95%" (τ = 0,896) custa **17 publicações**
em relação ao ponto de 37% e, *nesta amostra*, não compra precisão: a diferença é 1 erro.

## A tentação: a fronteira in-sample

| erro máximo | ponto | precisão | cota superior do erro | cobertura |
|---|---|---|---|---|
| 15% | 39/42 | 0,929 | 0,138 | 0,42 |
| 20% | 46/53 | 0,868 | 0,187 | 0,53 |
| 25% | 56/70 | 0,800 | 0,242 | 0,70 |

Lida ao pé da letra, a tabela agora começa em 15%: 39/42 se certifica com cota 0,138 e 42%
de cobertura — melhor que o ponto entregue em **tudo**. Nem o ponto de 37/36 se certifica a
10% depois da correção. Mas essa cota **ignora a seleção**: τ = 0,743 foi escolhido olhando
estes mesmos 100 rótulos. O instrumento que corrige isso é o conformal (CRC): a 10% de risco,
ele publica 49 com 40 acertos (**0,816**) e cobertura 0,49. O aninhado corrigido da
auditoria, para a política de maior cobertura, dá **13/17 = 0,765**. A diferença entre 0,973
e 0,77–0,82 **é o preço de escolher o limiar no conjunto que mede**.

## Robustez

**Bootstrap dos 100 rótulos** (regra fixa, 2000 reamostragens):

| grandeza | média | IC 95% |
|---|---|---|
| precisão | 0,950 | 0,833–1,000 |
| cobertura | 0,202 | 0,120–0,280 |

**Sensibilidade a τ** (consenso 0,75):

| τ | publicadas | acertos | precisão | cobertura |
|---|---|---|---|---|
| 0,856 | 23 | 22 | 0,957 | 0,23 |
| 0,876 | 20 | 19 | 0,950 | 0,20 |
| 0,886 | 20 | 19 | 0,950 | 0,20 |
| **0,896** | **20** | **19** | **0,950** | **0,20** |
| 0,906 | 16 | 15 | 0,938 | 0,16 |
| 0,916 | 13 | 12 | 0,923 | 0,13 |
| 0,936 | 11 | 10 | 0,909 | 0,11 |

Perto do ponto entregue, ±0,02 move poucas publicações (20 → 23 ou 16). A regra não está num
penhasco; está num platô.

## O que isso significa

1. **O ponto entregue é defensável, mas não é o de maior cobertura.** O protocolo escolheu o
   **maior** τ entre os que sustentam 95% com ≥ 20 publicadas, por proteção contra o
   otimismo. A curva mostra que essa proteção custa cobertura; não mostra que compra
   precisão fora da amostra — e as estimativas que corrigem a seleção (CRC 0,82; aninhado
   0,77) dizem que o platô de 0,97 não sobrevive.
2. **Não mover τ agora.** Mover para 0,736 depois de ver a curva é escolher o limiar no
   conjunto que mede — exatamente o que o protocolo proíbe. Nas 659, esse ponto publicaria
   **228** (34,6%), quase o dobro, com base em 100 rótulos e sem estimativa honesta que
   sustente 95%.
3. **O que o experimento entrega é o mapa, não a mudança.** A próxima rodada decide entre
   (a) manter o conservadorismo e entregar 0,95 com 17% de cobertura, ou (b) pré-registrar a
   política de maior cobertura e medi-la no aninhado — sabendo que a estimativa atual dessa
   política é ~0,77. É decisão de produto, tomada **antes** de ver o próximo resultado.

## Limitações

- A curva e a fronteira certificável são **in-sample**: o mesmo conjunto que escolheu τ. O
  CRC e o aninhado existem para corrigir isso, e é a eles que o relatório se ancora.
- 100 rótulos: 1 acerto = 1 ponto percentual; 0,95 e 0,97 são 1 erro de diferença.
- O bootstrap reamostra questões, não erros de rótulo; mede incerteza amostral, não a
  qualidade da folha-verdade.
- O ponto de 38% usa `cons ≥ 0,75`; a fronteira de `docs/auditoria.md` usa `cons = 1,0`
  (base mais estrita) e por isso começa em 32/31, não em 37/36.
