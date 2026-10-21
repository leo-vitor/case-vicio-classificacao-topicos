# Experimento 3 — recuperadores pareados, com IC e por disciplina

Pergunta: no texto enriquecido, algum recuperador bate o `rrf_all` no topo do ranking? E
onde a diferença aparece?

Reproduz com `python -m src.recuperadores` (~30 s). Artefato: `artefatos/recuperadores.json`.
Base: 92 válidas, texto `enri`, mesmos folds/insumos do restante do pipeline.

- **`ramo@k`** = algum dos k primeiros itens tem ramo aceito (tema central/extra promovido
  ao nível 1). É a métrica que decide o entregável.
- **`exato@k`** = algum dos k primeiros itens é o tema central/extra **sem** promoção. Mede
  a granularidade disponível, não o acerto da régua.

## ramo@k

| recuperador | ramo@1 | ramo@5 | ramo@10 |
|---|---|---|---|
| **rrf_all** | **0,739** | **0,935** | 0,946 |
| tfidf_char | 0,717 | 0,891 | 0,946 |
| tfidf | 0,598 | 0,913 | 0,946 |
| bm25 | 0,696 | 0,880 | 0,957 |

Delta pareado contra `rrf_all` no ramo@1 (IC bootstrap, 2000 reamostragens):

| recuperador | Δ ramo@1 | IC 95% | leitura |
|---|---|---|---|
| tfidf_char | −0,022 | −0,098..+0,054 | empate |
| bm25 | −0,044 | −0,109..+0,011 | empate |
| tfidf | −0,141 | −0,228..−0,065 | **pior** |

**Leitura.** Nenhum recuperador bate o `rrf_all` de forma significativa no top-1; o `tfidf`
isolado é significativamente pior (perde 13 pontos). No top-10 todos convergem (0,95): a
diferença entre eles é de **ordenação**, não de cobertura. Isso fecha a pergunta da Etapa 1
— não há ganho de arquitetura disponível na troca de recuperador com 92 questões.

## exato@k (sem promoção ao pai)

| recuperador | exato@1 | exato@5 | exato@10 |
|---|---|---|---|
| rrf_all | 0,446 | **0,761** | 0,848 |
| tfidf_char | **0,489** | 0,750 | 0,848 |
| tfidf | 0,337 | 0,739 | 0,837 |
| bm25 | 0,391 | 0,728 | 0,815 |

O `tfidf_char` é o melhor no **tema exato** no top-1 (0,489 contra 0,446), mas perde no
ramo (0,717 contra 0,739). A leitura é direta: o n-grama de caractere casa o título literal
do subtema com mais frequência; a fusão com BM25 escolhe melhor o **ramo**. Como o
entregável publica o ramo, o `rrf_all` continua campeão — mas o `char` é o melhor ponto de
partida se o produto um dia quiser o subtema.

## Por disciplina (ramo@1)

| disciplina | n | rrf_all | tfidf_char | tfidf | bm25 |
|---|---|---|---|---|---|
| Penal | 40 | **0,78** | 0,72 | 0,65 | 0,75 |
| Processo Penal | 30 | **0,73** | 0,67 | 0,60 | 0,70 |
| Legislação Especial | 12 | 0,50 | **0,58** | 0,25 | 0,33 |
| Criminologia | 10 | 0,90 | **1,00** | 0,80 | 0,90 |

Duas leituras:

1. **Legislação Especial é o ponto fraco de todos** (0,50 no `rrf_all`, melhor 0,58 no
   `char`). Com n = 12, uma questão vale 8 pontos percentuais: é um diagnóstico, não um
   ranking. Ainda assim, é o estrato onde o enriquecimento mais ajudou (antes, 0 publicações)
   e onde há mais espaço para melhorar o artefato.
2. **Criminologia** tem o `char` perfeito (10/10) e o `rrf_all` em 0,90 — um caso em que o
   n-grama de caractere bate o vocabulário mais técnico.

## O que isso decide

- **Não trocar o recuperador.** As diferenças no top-1 são menores que o ruído (exceto
  `tfidf`, que é pior) e a cobertura no top-10 é a mesma. Trocar seria mudança de
  arquitetura sem ganho demonstrado.
- **O gargalo segue na decisão**, como o Experimento 1 mostrou: 48 das 68 questões com
  top-1 certo são mandadas para revisão.
- **O próximo ganho de recuperação, se houver, é no artefato** (Legislação Especial), não na
  fusão de recuperadores.

## Limitações

- 92 questões; por disciplina, 10 a 40. As células por disciplina são descritivas.
- `exato@k` e `ramo@k` usam o mesmo ranking; a diferença é só a régua.
- O IC pareado cobre a diferença de médias; não cobre a escolha do melhor de 5×3 células.
  O máximo da grade não é adotado por esse motivo (mesmo cuidado do Experimento 2).
