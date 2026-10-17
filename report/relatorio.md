# Relatório: classificação de tópicos (máx. 5 páginas)

> **Rascunho.** A versão oficial do relatório é `report/relatorio.tex` (Overleaf/pdfLaTeX,
> 5 páginas, memo integrado como seção (d)). Este `.md` é mantido só como anotações; ele
> não é mais a fonte — evita divergência entre as duas versões.

> Números conferidos nos arquivos do repositório. Fontes: `docs/avaliacao.md`,
> `docs/dicionario_juridico.md`, `docs/irmaos_comparativo.md`, `docs/rotulos_opus.md`,
> `docs/ab_dicionario.md`, `docs/custo_por_mil.md`, `docs/auditoria_verificador.md`,
> `outputs/uso.json`.

## a) Abordagem e decisões

O desafio era classificar 359 questões em um catálogo de ~375 temas ativos, com
alta precisão e sem mandar tudo para revisão. Como muitos temas são parecidos ou
repetem nome entre disciplinas, não bastava pedir a um modelo que escolhesse uma
categoria: era preciso garantir que o tema certo estivesse entre as opções e
reconhecer quando não havia segurança para publicar.

A solução tem duas etapas. Primeiro, uma **busca textual** seleciona candidatos
(TF-IDF traz os 10 mais próximos, mais os pais e os filhos dos 3 primeiros).
Depois, **dois modelos** (`gemini-3.6-flash` e `gemini-3.1-flash-lite`) avaliam as
opções em **quatro votos**, consolidados por **regras**: votos iguais publicam; votos
em subtemas do mesmo ramo publicam no **nó comum** (a régua aceita pai/filho);
ramos diferentes vão para revisão; maioria de `fora` vira `fora`. Por fim, uma
**verificação adicional** encaminha para revisão quando discorda do resultado.

> **O resultado em três linhas**
> - **Operação:** 222 questões publicadas (61,8% das 359), 136 para revisão, 1 fora do escopo.
> - **Qualidade:** 54 acordos em 60 questões avaliadas — **90% de concordância** (limite inferior ~80%).
> - **O que os dados permitem concluir:** com rótulos de referência produzidos por IA, **não é possível confirmar** a meta de 95%.

Publicar no pai quando há dúvida entre filhos é deliberado: sob a régua, o pai é
**sempre aceito** se a verdade for um dos filhos votados — aposta de risco
assimétrico. Publicar menos (222 em vez de 261) reduz o risco de expor uma
classificação duvidosa, mas **não comprova** precisão de 95%.

**Onde eu errei de verdade.** O gargalo é a **busca**, não a decisão: dos 93
rótulos, 11 nunca apareceram entre as opções oferecidas; em cerca de **88%**, a
busca incluiu o tema certo ou um diretamente relacionado (**recall hierárquico de
0,88**). Dos 11 erros publicados, 6 são de busca e 5 de decisão, e **todos os 11
são votos unânimes**: quando a busca trouxe as opções erradas, os dois modelos
concordaram no erro. Ou seja, a concordância sozinha **não sinaliza o erro**.

**O que tentei e descartei.** Uma política seletiva publicava só as questões de
maior certeza (chegou a 95 das 359), mas apoiava-se em ~17 rótulos e na mesma
amostra — Wilson frágil (0,82 e 0,61). Descartei-a.

**A verificação.** Como os erros são unânimes e por falha de busca, adicionei um
**5º voto** de um modelo que pode consultar **todos os temas** (**verificador com
árvore inteira**, `flash-lite`): se ele discorda do tema publicado, a questão vai
para revisão — a única forma de pegar o erro "confiante e errado".

**O que fiz com esse diagnóstico.** Como o gargalo é a busca e se concentra em
**legislação especial**, ataquei o ponto **offline** (sem alterar a entrega):
enriqueci a consulta com um **dicionário jurídico** e testei a expansão por
**irmãos** — resultados na seção (b), inclusive numa **segunda rotulagem**.

## b) Diagnóstico

**Números (93 questões rotuladas por IA: texto da questão e lista de temas).**

| Métrica | Valor |
|---|---|
| Concordância observada (base 261) | 0,838 (57/68) |
| Concordância observada (após verificador, 222) | **0,90 (54/60)** |
| Wilson 95% da entrega | [0,80; 0,95] |
| Recall dos candidatos (base) | 0,882 (82/93) |
| Erros publicados (base) | 11 → 6 de busca, 5 de decisão |

**Advertência metodológica.** Os rótulos vêm de outro LLM (**DeepSeek**): o 0,90 é
**concordância entre modelos**, não precisão contra especialistas — que permanece
**desconhecida**. Não afirmo os 95%: com 54/60 o observado é 90% e o Wilson, ~80%.

**Como o catálogo atrapalha.** (1) **Gêmeos** — títulos iguais em disciplinas
diferentes (16 ids, 8 pares); como a régua não distingue, ficam em revisão. (2)
**Lixeiras** — temas com muitas questões na origem (≥40): 130 das 261 publicadas
(50%), acerto 35/40 na amostra. (3) **Sobreposição** pai/filho — é o que a
estratégia do nó comum explora a favor.

**Onde o erro se concentra.** Em **legislação especial de Penal e Processo Penal**
e em assertivas I–IV com pouca pista lexical. O padrão é claro: quando o tema certo
**não é oferecido**, o juiz escolhe, de forma unânime, o vizinho mais próximo.

**Ataque ao ponto fraco: legislação especial.** Duas alavancas, testadas offline e
confirmadas em dev × holdout:

1. **Dicionário jurídico** (`data/dicionario_juridico.csv`, 62 entradas conferidas à
   mão): traduz a citação da questão para o termo do título do tema (ex.: "Lei
   11.340" → "Lei Maria da Penha") — fecha o descompasso de vocabulário da busca lexical.
2. **Expansão por irmãos:** acrescenta temas do mesmo assunto sob a mesma categoria-mãe.

| Mecanismo de busca (k=10) | `recall_hier` (93) | Legislação Especial |
|---|---|---|
| Atual (TF-IDF + pais/filhos) | 0,667 | 5/19 (~26%) |
| + dicionário (`top+dic`) | 0,731 | 12/19 |
| + irmãos, sem dicionário | 0,882 | 9/19 |
| **dicionário + irmãos** | **0,957** | **16/19 (~84%)** |

No **holdout** a melhora se mantém (0,613 → **0,968**; Legislação Especial
**2/6 → 6/6**). Ressalva honesta: a **última expansão** do dicionário foi decidida
olhando os erros remanescentes — **um deles no holdout** (`Q0333`) —, então o 0,968
**não é um holdout estritamente cego**. O dicionário sobe o **piso** (0,667 → 0,731
sozinho); os **irmãos**, o topo; somados, 0,957. A busca **densa** (embeddings)
**não** superou a textual.

**Teste fim-a-fim (A/B pago, nível da decisão).** Levei o dicionário até a decisão
na rotulagem Opus (148 questões, out-of-sample), mesmos modelos e regras, com o
verificador anexado:

| Config | `recall_hier` | Publicação correta (c/ verificador) |
|---|---|---|
| `filho` (controle limpo) | 0,791 | 0,886 (78/88) |
| `filho+dic` (dicionário) | 0,845 | 0,888 (79/89) |

O dicionário **sobe o recall** (+5,4 pp) mas muda a decisão **+0,2 pp** (1 questão):
**8 dos +10 acertos extras caem em `revisar`** (o juiz acha o tema, a agregação não
publica) — a métrica conta só as publicadas. No pareado: **+2 conserta / −1 quebra /
8 neutras**. Por isso **não foi adotado**: o ganho de busca não se converte em
publicação. Decomposição: `docs/ab_dicionario.md`.

**Nada disso entrou no `publicacao.csv`**: mudar a lista de candidatos invalida o
cache do juiz e exigiria re-julgar (custo).

**Robustez: segunda rotulagem independente.** Recriei os testes em **150 questões
rotuladas por outro modelo (Opus)** (`data/rotulos_opus.tsv`), sem tocar na entrega:

| Medida | Resultado |
|---|---|
| Pipeline congelado × nova rotulagem (88 publicadas) | **0,92 hierárquico** (0,77 exato) |
| Escolha de **gêmeo** publicada | **0** nos casos avaliados (exposição pequena) |
| Melhor recuperação (`recall_hier`) | 0,791 → **0,973** (dicionário + irmãos) |
| Legislação Especial (28) | 16 → **25/28** |
| Entre as 60 não publicadas | tema recuperável em 46; sugestão já correta em 31 |

**Nota sobre gêmeos.** A **convenção** para temas de título duplicado **não foi
confirmada** pela organização. Nas questões avaliadas **não observei erro por escolha
de gêmeo**, mas a exposição é pequena (poucos gêmeos publicados): trato como
**ausência de evidência**, não como garantia.

**As duas rotulagens concordam no ramo, não no tema exato.** Nas **41 questões**
comuns (antiga, DeepSeek; nova, Opus), o acordo é **0,54 exato** e **0,85
tema/pai/filho** — o achado mais importante para o professor: **a conclusão é
sensível a quem rotula**, e qualquer "precisão" aqui é **concordância com um
conjunto de rótulos específico**. O erro, porém, acompanha a **incerteza do rótulo**:
nas publicadas, a concordância é 1,00/0,98 (hierárquica/exata) quando o rótulo é
de baixa dúvida e cai para 0,73/0,46 quando é de alta.

**O custo de ampliar a busca (gêmeos).** Lista maior **expõe** a mais gêmeos (mesmo
título, disciplina diferente): o gêmeo *do tema certo* sai de **4** (config atual)
para **9** com o dicionário e **10** com irmãos + dicionário. É o **dicionário** —
não os irmãos — que injeta a exposição, e com **lista menor que a atual** (mais
barato); irmãos multiplicam a lista por **~6×** com ganho marginal. Como a régua não
distingue gêmeos, o `decide.py` **rebaixa** para revisão — o efeito provável é
**perder cobertura**, não publicar errado.

## c) Produção (50 mil questões por semana)

> O que segue é **proposta**; **não foi executado nesta entrega** (orçamento de API
> esgotado e prazo curto) — é o plano para a próxima fase.

**Arquitetura proposta** (do barato para o caro):

1. **Recuperação ampliada** — manter o TF-IDF e adicionar o **dicionário jurídico**
   (grátis) e a **expansão por irmãos** (grátis); se houver GPU, **embeddings
   densos** jurídicos (Legal-BERTimbau). O dicionário sobe o piso; os irmãos, o topo.
2. **Classificador treinado** — após acumular rótulos dos professores, um modelo leve
   resolve a maioria e devolve **probabilidade calibrada**.
3. **LLM + verificação seletiva** — juiz barato nos casos fáceis; verificador com a
   árvore inteira só nos ambíguos; **revisão humana** nas divergências.

**Custo por 1.000 questões.** No último run do juiz (`outputs/uso.json`): 945.992
tokens de entrada, 9.188 de saída e 30.660 de raciocínio para as 359 questões em 4
votos, em 89,1 s (~8.446 de entrada/chamada). É **parcial** (fallback e verificação
não registravam uso) e as 112 chamadas novas foram do **fallback** com a árvore
inteira → **teto**. Projeção: **~33,8 M tokens de entrada / 1.000 questões**. Com a
tabela pública de out/2026 (a confirmar no contrato):

| Faixa de preço (in/out por M) | Por 1.000 | 50 mil/semana |
|---|---|---|
| US$ 0,10 / 0,40 (Flash-Lite) | **US$ 3,51** | US$ 176 |
| US$ 0,30 / 2,50 (Flash médio) | **US$ 10,96** | US$ 548 |
| US$ 0,75 / 3,75 (Flash topo) | **US$ 26,57** | US$ 1.329 |

Há sinal de **dobra de preço em 01/01/2027** — por isso a produção troca o LLM por
recuperação + classificador nos casos fáceis: a parte local é **grátis** e já
resolve o gargalo de busca.

**Cache de contexto (alavanca de custo).** O bloco repetido (instruções + árvore,
~9 mil tokens) pode ser enviado **uma vez** e reaproveitado nas demais chamadas.
O plano em tokens é **grátis** (`--dry-run`: ~72% de economia na entrada); o teste
real é **pequeno, a saída não foi guardada** e os créditos de API acabaram, então
não o reexecutei (`docs/cache_contexto.md`). É a alavanca de custo mais direta na
produção — mas **confirmar o desconto real no contrato**: medimos **tokens**, não preço.

**Medição contínua:** (i) amostra auditada por professor toda semana, na régua
pai/filho; (ii) taxa de revisão e de correção na fila; (iii) reportes de alunos;
(iv) **cobertura a precisão fixa** — a métrica que importa.

**Meta de 95%.** Sem gabarito humano, não há garantia formal. A entrega prioriza
precisão (votação, recuperação ampliada, verificação e revisão dos discordantes) e
uma avaliação honesta. Ressalva que deve constar: não afirmamos que os 95% foram
atingidos — a precisão real é desconhecida.

## Glossário (para leitores não técnicos)

| Termo técnico | Como ler |
|---|---|
| Recuperação de candidatos | Busca das categorias mais relevantes para cada questão |
| Recall hierárquico | Frequência com que a busca acha o tema correto ou um diretamente relacionado |
| Dicionário jurídico | Tradução de citações de leis para os nomes que aparecem nos títulos dos temas |
| Temas gêmeos | Temas com o mesmo nome em disciplinas diferentes — indistinguíveis pela régua |
| Votos unânimes | Os quatro julgamentos concordaram — inclusive em alguns erros |
| Verificador com árvore inteira | Segunda checagem que pode consultar todos os temas disponíveis |
| Concordância (vs. precisão) | O quanto o resultado bate com rótulos de referência, e não necessariamente com o gabarito de especialistas |

## d) Memo para o professor (1 página)

Veja `report/memo_professor.md`.
