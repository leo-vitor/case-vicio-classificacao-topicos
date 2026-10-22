# Rodada 2: evidência legal e aprendizado ativo

Base: ramo `experimentos`, criado a partir de `v4-entrega-final`. Nada aqui altera
`publicacao.csv`, `previsao.txt` ou o relatório do `main`.

Regras gerais:

- nenhum modelo de linguagem na decisão;
- as tabelas `experimentos/artigos_tema.csv` e `experimentos/leis_tema.csv` são
  propostas por LLM, não revisadas por humano, e entram apenas como dado versionado;
- todo número de precisão ou cobertura usa o protocolo aninhado corrigido, com cinco
  dobras repetidas cinco vezes e limiar escolhido dentro da dobra;
- todo resultado vem com intervalo de Wilson e comparação pareada contra o baseline;
- sinal com menos de cinco casos positivos na folha não vira peso de modelo.

## Etapa 0. Ramo e proveniência

Hipótese: as três tabelas propostas são insumo suficiente para um teste exploratório,
desde que a proveniência e o status de revisão fiquem explícitos.

Critério: o ramo `experimentos` existe, os três arquivos estão versionados e o
`PROVENIENCIA.md` foi lido antes de qualquer teste. Nenhuma alteração no `main`.

Resultado: ramo `experimentos` criado; `artigos_tema.csv`, `leis_tema.csv` e
`PROVENIENCIA.md` versionados no commit `73f9fa0`; nenhuma alteração no `main`.

Decisão: seguindo para as checagens, com as tabelas tratadas como proposta não revisada.

## Etapa 1. Checagem mecânica das tabelas

Hipótese: as tabelas podem ter erros mecânicos de tema, faixa ou sufixo, mesmo sem
erro jurídico.

Critério: verificar, sem validar juridicamente:

- todo `tema_id` existe em `data/temas.csv` e está `active`;
- faixas fora de ordem ou sobrepostas dentro do mesmo código;
- artigos com sufixo e a regra de que sufixo casa apenas com a linha de mesmo sufixo;
- linhas marcadas como `catálogo original: tema irmão de 5155`;
- números de lei repetidos ou temas inativos em `leis_tema.csv`.

O produto é uma lista do que precisa de revisão humana, não uma decisão jurídica.

Resultado: 227 linhas de artigos e 27 de leis; todos os `tema_id` existem e estão
ativos; 0 faixas fora de ordem; 0 sobreposições reais de identidade (número + sufixo);
36 linhas com sufixo, sendo 35 cobertas pela regra e 1 faixa mista (`CPP 317..318-B`);
2 linhas de catálogo original, ambas com pai atual 5155; 0 números de lei repetidos;
1 lei marcada como revogada (Lei 4.898/1965). Lista completa em
`artefatos/experimentos/checagem_tabelas.md`.

Decisão: revisão humana necessária para a faixa mista do CPP, para a lei revogada e
para a conferência jurídica geral das tabelas. A checagem mecânica não encontrou
colisão de identidade.

## Etapa 2. Extrator determinístico

Hipótese: é possível extrair artigos e leis citados com regras de texto e mapeá-los
para ramos, sem LLM e sem olhar o gabarito.

Critério: criar `src/experimentos/evidencia_legal.py` e salvar, por questão, as fontes
encontradas, os ramos indicados e se há um ramo único. Separar CP Parte Geral (arts.
1 a 120), CP Parte Especial (121 em diante), CPP e lei especial. Reportar cobertura nas
659 e na folha, com denominadores explícitos.

Resultado: 132/659 questões com evidência mapeada e 114/659 com ramo único geral;
na folha, 20/100 com evidência e 17/100 com ramo único geral. Por fonte, nas 659:
CP Parte Geral 20, CP Parte Especial 32, CPP 23, lei especial 69; na folha: 6, 7, 1 e
9. Saídas em `artefatos/experimentos/evidencia_legal.csv` e `.jsonl`.

Decisão: extrator determinístico usado nas etapas seguintes; cobertura baixa é uma
limitação explícita, não um resultado escondido.

## Etapa 3. Diagnóstico na folha

Hipótese pré-registrada: CP Parte Geral, CPP e lei especial indicam o assunto;
CP Parte Especial indica o cenário e erra mais.

Critério: para cada fonte, restringir às questões da folha com um único ramo indicado.
Calcular acerto da evidência pela régua do case (tema central, extra, pai ou filho),
acerto do modelo no mesmo subconjunto e o cruzamento entre os dois. Reportar n,
acertos e intervalo de Wilson.

Uma fonte passa para a Etapa 4 somente se, no subconjunto único:

- tiver pelo menos cinco casos;
- o acerto da evidência for maior ou igual ao acerto do modelo;
- o pareado por questão tiver mais ganhos que perdas.

Se não passar, fica fora da decisão e vai para a lista de revisão humana.

Resultado: na folha, CP Parte Geral 5/6 (IC 0,44-0,97) contra modelo 5/6, com 1
ganho e 1 perda; CP Parte Especial 3/6 (IC 0,19-0,81) contra 4/6, com 0 ganhos e 1
perda; CPP 1/1 (IC 0,21-1,00), sem tamanho para peso; lei especial 7/9 (IC 0,45-0,94)
contra 4/9 (IC 0,19-0,73), com 3 ganhos e 0 perdas. O teste exploratório de 8/9 não
se reproduz: Q0090 cita a Lei 9.099 em alternativa distratora. A união exploratória
dos artigos dá 6/9 contra 5/9, mas mistura Parte Geral e Parte Especial.

Decisão: só lei especial passa no critério escrito. A hipótese não se confirma como
um todo: CP Parte Especial erra mais que o modelo, mas CP Parte Geral empata e CPP
tem apenas um caso. CP Parte Geral fica como sugestão, não como peso.

## Etapa 4. Evidência legal na decisão

Hipótese: usar a evidência como veto ou como promoção melhora a decisão sem cair a
precisão.

Critério de adoção, escrito antes do teste:

- usar apenas as fontes que passaram na Etapa 3;
- comparar cada variante com o baseline no mesmo protocolo aninhado;
- manter a escolha de `(tau, consenso)` do baseline em cada dobra de treino e aplicar
  veto ou promoção somente no teste;
- adotar somente se a precisão aninhada não cair, a cobertura aninhada subir e o
  pareado por questão mostrar mais ganhos que perdas.

Formas testadas:

1. **Veto:** se há ramo único pela evidência e ele difere do ramo que o baseline
   publicaria, a questão vai para revisão.
2. **Promoção:** se há ramo único pela evidência, ele coincide com o top-1 e o
   consenso é pelo menos 0,75, publica mesmo abaixo do limiar.

O veto, por construção, só pode reduzir publicações. Se o critério de cobertura não
puder ser satisfeito, isso será registrado como resultado, não contornado.

**Defeito do critério do veto.** Exigir que a cobertura suba é incompatível com um
veto: vetar só transforma `publicar` em `revisar`, nunca cria uma publicação nova.
Logo, o veto não pode passar nesse critério, independentemente de sua precisão. O
teste mede corretamente o efeito, mas o critério de adoção está mal desenhado para
essa forma. Para uma próxima rodada, o veto deveria ser julgado por precisão e por
perdas evitadas, não por aumento de cobertura.

Definição operacional, escrita antes de rodar: o baseline é a regra atual
`(consenso >= c) & (p >= tau)`, com `(tau, c)` escolhidos dentro do treino de cada
uma das 25 dobras externas (5 repetições de 5 dobras). Em cada dobra, a variante
recebe a mesma decisão do baseline e aplica veto ou promoção apenas no teste. Cada
repetição é medida separadamente; para o pareado por questão, uma questão conta como
publicada se aparecer publicada em pelo menos 3 das 5 repetições, e o acerto é o da
maioria das repetições em que foi publicada. O intervalo de Wilson é calculado sobre
essa máscara majoritária. A média e a faixa entre repetições também são reportadas.

Resultado: a fonte lei especial tem 9/100 questões com ramo único. O veto mudou 3
publicações (dobra x questão) e não mudou a máscara majoritária; a promoção adicionou
10 publicações (dobra x questão). Na agregação majoritária pré-registrada, baseline
29/30 (0,967; IC 0,83-0,99), veto 29/30 e promoção 30/32 (0,938; IC 0,80-0,98).
A agregação majoritária, porém, é otimista: a média por repetição do baseline é
0,889 (faixa 0,765-0,971) e a cobertura média é 0,276. O baseline de 5 dobras já
existente continua 13/17 (0,765; IC 0,53-0,90). Na leitura por repetição, o veto
fica em 0,910 de precisão e 0,270 de cobertura; a promoção fica em 0,862 e 0,296.
O veto perde cobertura e a promoção cai precisão; ambos falham no critério.

Decisão: nenhuma das duas formas é adotada. Veto e promoção ficam registrados como
beco sem saída para esta fonte; a agregação majoritária não deve ser usada como
número principal.

**Observação sobre o baseline.** O 0,889 é a média das cinco repetições, cada uma com
cinco dobras; o 0,765 é a partição única de 5 dobras que já estava no relatório
(13/17). São estimativas de protocolos diferentes, não dois números concorrentes. O
0,889 não deve substituir o 0,765 como número principal: a repetição reduz ruído de
uma partição, mas não cria uma amostra nova, e a agregação por maioria entre
repetições infla a precisão. O número público continua 0,765 [0,53-0,90].

## Etapa 5. Simulação de aprendizado ativo

Hipótese: escolher o que rotular por incerteza ou por evidência legal rende mais do
que escolher ao acaso.

Critério: simular, na folha, a adição de 10, 20 e 40 rótulos a um conjunto inicial
fixo. Comparar quatro estratégias: ao acaso, mais perto do limiar, com evidência legal
e Legislação Especial primeiro. Medir precisão e cobertura no conjunto de teste com o
mesmo protocolo aninhado. Repetir com pelo menos 20 sementes e reportar média e faixa.
Não adotar nenhuma estratégia; o produto é evidência para a seção de produção.

Definição operacional, escrita antes de rodar: em cada semente, 40 questões da folha
formam o teste e 60 formam o pool, com estratificação pela disciplina do tema central.
O conjunto inicial tem 20 rótulos sorteados do pool. A cada bloco, o modelo é
reajustado e o limiar é escolhido por validação interna de 5 dobras apenas no conjunto
rotulado; depois são adicionados 10, 20 ou 40 rótulos do pool, em blocos de 10. As
estratégias são: sorteio uniforme; menor distância ao limiar vigente; prioridade para
questões com ramo único de evidência legal; e prioridade para o ramo previsto de
Legislação Especial. O teste nunca entra no treino nem na escolha do limiar. Serão 30
sementes; reportamos média, mínimo e máximo de precisão e cobertura no teste.

Resultado: 30 sementes; a precisão é calculada só nas sementes com pelo menos uma
publicação no teste. Precisão média: acaso 0,89-0,92; limiar 0,91-0,92; evidência
0,93; Legislação Especial 0,89-0,93. Cobertura média: acaso 0,24-0,26; evidência
0,17-0,19; as demais entre 0,16 e 0,24. Em +10, a evidência teve 10 vitórias, 9
empates e 6 derrotas de precisão contra o acaso, mas perdeu cobertura em 19 de 30
sementes. Em +20 e +40 o padrão se repete: precisão um pouco maior, cobertura menor.
Nenhuma estratégia domina as duas métricas.

Decisão: nenhuma estratégia é adotada. O resultado é evidência para a produção:
com 10 a 40 rótulos adicionais, a escolha ativa não bate o sorteio de forma estável.
Priorizar evidência legal compra precisão ao custo de cobertura; se a produção quiser
menos revisão e mais publicações, o sorteio ainda é a referência.

## Etapa 6. Estabilidade entre visões

Hipótese: a concordância entre busca no enunciado, nas alternativas e no comando
separa acertos de erros.

Critério descritivo: rodar as três buscas e medir a concordância do ramo top-1 entre
as visões. Comparar o acerto do modelo entre questões com as três visões concordantes
e questões com pelo menos uma discordância. Só transformar em teste aninhado se a
separação for clara, definida antes como diferença de pelo menos 15 pontos percentuais
entre os grupos, com pelo menos 10 questões em cada grupo. Caso contrário, fica
descritivo.

Definição operacional, escrita antes de rodar: enunciado, alternativas e comando são
extraídos do JSONL original com a mesma limpeza de HTML. A busca usa `rrf_all` sobre
os temas enriquecidos; a visão de uma questão é o ramo do top-1 promovido. As três
visões são concordantes quando dão o mesmo ramo. O acerto comparado é o do modelo de
texto completo, `pred`, pela régua do case. Reportamos n, acerto e Wilson por grupo;
a diferença é em pontos percentuais.

Resultado: 6/100 questões tiveram as três visões concordantes, com 6/6 acertos
(IC 0,61-1,00); as 94 com alguma discordância tiveram 62/94 (0,660; IC 0,56-0,75).
A diferença é de 34 pontos percentuais, mas o grupo concordante tem só 6 casos, abaixo
do mínimo de 10 definido no critério.

Decisão: a separação não é clara pelo critério; fica descritiva e não vira teste
aninhado. O sinal é sugestivo, mas pequeno demais para decidir.
