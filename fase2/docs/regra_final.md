# Experimento 5 — regra final: curva precisão × cobertura e robustez

Pergunta: a regra entregue está num ponto razoável da curva, ou foi um pico de sorte? E
quanto ela se move com o ruído de 100 rótulos?

Reproduz com `python -m src.regra_final` (~10 s). Artefato: `artefatos/regra_final.json`.
Usa `p_oof` (probabilidade fora da dobra) e o consenso do top-1 — as grandezas que
escolheram a regra. A cota de Clopper-Pearson é **unilateral**, a mesma de
`src/conformal.py`, para que as duas fronteiras sejam comparáveis.

## Ponto entregue

`consenso ≥ 0,75` e `p ≥ 0,887009` → **19/20 = 0,950**, Wilson [0,764; 0,991], cobertura
0,20 na folha. Nas 659: **118 publicar / 541 revisar**.

Cota superior do erro (Clopper-Pearson): **0,159 a 15%** e **0,142 a 20%**. Ou seja, o ponto
entregue só se certifica a 20% de erro — a 15% ele não passa.

## Curva (consenso fixo em 0,75)

Melhor precisão em cada nível de cobertura:

| cobertura | τ | publicadas | acertos | precisão | Wilson inf. |
|---|---|---|---|---|---|
| ≥ 0,05 | 0,969 | 6 | 6 | 1,000 | 0,610 |
| ≥ 0,10 | 0,736 | 38 | 37 | **0,974** | 0,861 |
| ≥ 0,40 | 0,689 | 41 | 38 | 0,927 | 0,806 |
| ≥ 0,50 | 0,502 | 55 | 48 | 0,873 | 0,762 |
| **entregue** | **0,887** | **20** | **19** | **0,950** | **0,764** |

**A curva é plana entre 20% e 38% de cobertura** (0,950 → 0,974) e só cai depois de 40%.
O critério "mais conservador entre os que sustentam 95%" (τ = 0,887) custa **18 publicações**
em relação ao ponto de 38% e, *nesta amostra*, não compra precisão: a diferença é 1 erro.

## A tentação: a fronteira in-sample

| erro máximo | ponto | precisão | cota superior do erro | cobertura |
|---|---|---|---|---|
| 10% | 37/38 | 0,974 | 0,099 | 0,38 |
| 15% | 38/41 | 0,927 | 0,141 | 0,41 |
| 20% | 48/56 | 0,857 | 0,197 | 0,56 |
| 25% | 55/69 | 0,797 | 0,246 | 0,69 |

Lida ao pé da letra, a tabela diz que 37/38 se certifica a 10% de erro com 38% de cobertura
— melhor que o ponto entregue em **tudo**. Mas essa cota **ignora a seleção**: τ = 0,736 foi
escolhido olhando estes mesmos 100 rótulos. O instrumento que corrige isso é o conformal
(CRC): a 10% de risco, ele publica 48 com 39 acertos (**0,813**) e cobertura 0,48. O
aninhado corrigido da auditoria, para a política de maior cobertura, dá **13/15 = 0,867**.
A diferença entre 0,974 e 0,81–0,87 **é o preço de escolher o limiar no conjunto que mede**.

## Robustez

**Bootstrap dos 100 rótulos** (regra fixa, 2000 reamostragens):

| grandeza | média | IC 95% |
|---|---|---|
| precisão | 0,950 | 0,833–1,000 |
| cobertura | 0,202 | 0,120–0,280 |

**Sensibilidade a τ** (consenso 0,75):

| τ | publicadas | acertos | precisão | cobertura |
|---|---|---|---|---|
| 0,847 | 22 | 21 | 0,955 | 0,22 |
| 0,867 | 22 | 21 | 0,955 | 0,22 |
| 0,877 | 21 | 20 | 0,952 | 0,21 |
| **0,887** | **20** | **19** | **0,950** | **0,20** |
| 0,897 | 18 | 17 | 0,944 | 0,18 |
| 0,907 | 16 | 15 | 0,938 | 0,16 |
| 0,927 | 13 | 12 | 0,923 | 0,13 |

Perto do ponto entregue, ±0,02 move poucas publicações (20 → 22 ou 16). A regra não está num
penhasco; está num platô.

## O que isso significa

1. **O ponto entregue é defensável, mas não é o de maior cobertura.** O protocolo escolheu o
   **maior** τ entre os que sustentam 95% com ≥ 20 publicadas, por proteção contra o
   otimismo. A curva mostra que essa proteção custa cobertura; não mostra que compra
   precisão fora da amostra — e as estimativas que corrigem a seleção (CRC 0,81; aninhado
   0,87) dizem que o platô de 0,97 não sobrevive.
2. **Não mover τ agora.** Mover para 0,736 depois de ver a curva é escolher o limiar no
   conjunto que mede — exatamente o que o protocolo proíbe. Nas 659, esse ponto publicaria
   **238** (36,1%), quase o dobro, com base em 100 rótulos e sem estimativa honesta que
   sustente 95%.
3. **O que o experimento entrega é o mapa, não a mudança.** A próxima rodada decide entre
   (a) manter o conservadorismo e entregar 0,95 com 18% de cobertura, ou (b) pré-registrar a
   política de maior cobertura e medi-la no aninhado — sabendo que a estimativa atual dessa
   política é ~0,87. É decisão de produto, tomada **antes** de ver o próximo resultado.

## Limitações

- A curva e a fronteira certificável são **in-sample**: o mesmo conjunto que escolheu τ. O
  CRC e o aninhado existem para corrigir isso, e é a eles que o relatório se ancora.
- 100 rótulos: 1 acerto = 1 ponto percentual; 0,95 e 0,97 são 1 erro de diferença.
- O bootstrap reamostra questões, não erros de rótulo; mede incerteza amostral, não a
  qualidade da folha-verdade.
- O ponto de 38% usa `cons ≥ 0,75`; a fronteira de `docs/auditoria.md` usa `cons = 1,0`
  (base mais estrita) e por isso começa em 32/31, não em 37/38.
