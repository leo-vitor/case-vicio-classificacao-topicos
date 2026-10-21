# Procedência do `enriquecimento_v01.jsonl`

Registro de como cada objeto do artefato foi produzido, com modelo, data e validação.
O arquivo é insumo **offline e versionado**: o pipeline (`clean` → `baseline` → `confianca` →
`decisao` → `previsao`) não chama LLM nem rede. O artefato é lido do disco como qualquer
outro CSV de `data/`.

## Arquivo

| campo | valor |
|---|---|
| caminho | `fase2/enriquecimento_v01.jsonl` |
| linhas | 351 (universo enriquecível completo) |
| bytes | 198.608 |
| sha256 | `7bbda02e4c658484` |
| contiguidade | sem buracos, sem duplicados, sem fora do universo |
| contrato | 351 ok, 0 reprovados, 9 avisos (8 colisões legítimas entre irmãos + 1 linha longa) |

Universo enriquecível = 375 nós `active` de nível ≥ 1 menos 20 duplicatas de nível 1 não
enriquecíveis (6716–6728 e 6732–6738) menos os 4 nós raiz = **351**.

## Modelos

| faixa de objetos | ids | modelo | data |
|---|---|---|---|
| 1–172 | 5063–5467 | Gemini (execução externa, offline, colada no ingestor) | 2026-10-19/20 |
| 173–351 | 5468–4709 | DeepSeek V4.1 Flash (esta sessão) | 2026-10-20 |

O corte em 5467/5468 é a fronteira do checkpoint de 172 objetos. A partir de 5468 todo o
conteúdo foi gerado nesta sessão, em rodadas de 13 a 21 objetos.

## Rodadas (segunda faixa)

| rodada | objetos | ids | validação |
|---|---|---|---|
| 1 | 41 | 5468–5508 | ok (auditoria posterior corrigiu 13 objetos) |
| 2 | 21 | 5509–5529 | 1 erro corrigido (instituto de 37 chars em 5513) |
| 3 | 13 | 5530–5542 | 1 erro corrigido (distinção para não-irmão em 5532) |
| 4 | 17 | 5543–5559 | ok; 3 institutos genéricos trocados por específicos |
| 5 | 20 | 5560–5579 | 2 erros corrigidos (colisão pai/filho em 5572/5577) |
| 6 | 21 | 5580–4370 | 4 erros corrigidos (colisão pai/filho, distinção, instituto longo) |
| 7 | 20 | 4371–4390 | 1 erro corrigido (distinção para não-irmão em 4390) |
| 8 | 13 | 4684–4696 | 6 leis fora da whitelist removidas + 1 instituto longo |
| 9 | 13 | 4697–4709 | ok; 1 colisão entre irmãos trocada |

Cada rodada foi validada pelo mesmo validador antes de gravar. A única correção retroativa
foi a auditoria do checkpoint de 172: 30 violações de contrato em 13 objetos (blacklist,
textos curtos, institutos longos, colisões pai→filho e entre irmãos), todas corrigidas
antes de o validador entrar em uso.

## Convenções

- títulos copiados literalmente de `data/temas.csv`, inclusive erros de digitação
  (`Caractéristas`, `Escolas Crimonológicas`, `Estaturo de Idoso`, `Carta Testemunhavel`)
  e o prefixo `2 ` em 5531;
- `id_tema` como string;
- `sinonimos`: 2 a 5 termos, sem repetir o título;
- `institutos`: 0 a 5, até 35 caracteres;
- `texto_enriquecido`: 120 a 250 caracteres;
- `distincoes`: 0 a 3, sempre entre irmãos;
- `leis`: só as 21 chaves da whitelist de `data/dicionario_juridico.csv`;
- sem número de processo, julgado, súmula ou URL nos campos.

## Avisos remanescentes (legítimos)

Colisões entre irmãos que compartilham o instituto de propósito:

- 5469/5472 — princípio da oportunidade (duas faces do mesmo princípio);
- 5522/5523 — fiança (cautelar diversa e liberdade provisória);
- 5546/5549 — contraditório (perícia e declaração do ofendido);
- 5570/5571 — prequestionamento (extraordinário e especial).

## Decisão de taxonomia (v02, 2026-10-20)

Conferida a Lei 14.197/2021 na fonte oficial (Planalto), o Título XII do Código Penal tem:

| dispositivo | conteúdo | artigos |
|---|---|---|
| Cap. I | soberania nacional | 359-I a 359-K |
| Cap. II | instituições democráticas | 359-L, 359-M |
| Cap. III | instituições democráticas no processo eleitoral | 359-N, 359-P |
| Cap. IV | funcionamento dos serviços essenciais | 359-R (sabotagem) |
| Cap. VI | disposições comuns | 359-T |

Portanto:

- **5148 e 5155 não são duplicatas — são aninhados.** 5155 é o Título XII; 5148 é o
  Capítulo II. Os dois foram reparentados em `src/taxonomia.py` (5148 e 5156 passam a ser
  filhos de 5155, nível 2), sem mudar IDs.
- **5156 estava errado.** Não são os arts. 265–266 (incolumidade pública): é o Capítulo IV,
  art. 359-R (sabotagem). O objeto foi reescrito.
- **5148 também foi corrigido.** O instituto "interrupção do processo eleitoral" pertence ao
  Capítulo III e foi removido; entraram "abolição violenta do Estado" e "depor governo
  constituído".
- 5148 e 5156 ganharam uma `distinção` entre si, agora que são irmãos.

Impacto medido: 8 temas previstos mudam, 18 decisões mudam, e nenhuma das 15 publicações
perdidas troca de tema — a mudança atravessou o limiar pela confiança, não pela busca.

## Como reproduzir a validação

```bash
cd fase2
.venv/bin/python scripts/ingerir.py --auditar          # contrato + contiguidade + hash
.venv/bin/python scripts/ingerir.py --auditar --csv    # mesmo, com detalhe por objeto
.venv/bin/python scripts/ingerir.py --proxima 20       # próxima rodada (se houver)
```
