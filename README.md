# Case Vício (Método VDE): classificação de tópicos

Classifica cada uma das **359 questões** de concurso num tema de Direito, ou manda
para **revisão**: votação de dois LLMs, recuperação ampliada e uma segunda checagem.

- **Resultado:** **222 publicadas** (61,8%), **136 para revisão**, **1 fora do escopo**.
- **Qualidade:** **0,90 de concordância** (54/60) nas publicadas, com limite inferior
  de Wilson ~80%. Isso **não** é precisão contra especialistas: os rótulos vieram de
  outro LLM (DeepSeek); mede-se concordância, não precisão.
- **Previsão (`previsao.txt`):** **0,86 (0,74 a 0,94)**, cobertura 0,62, revisada
  após a segunda rotulagem. A meta de **95% não está demonstrada**.
- **Rodar (sem API):** `python -m src.clean && python -m src.decide && python -m src.validate`
  (detalhes em [Como rodar](#como-rodar)).
- **Relatório (5 páginas):** [`report/relatorio.pdf`](report/relatorio.pdf); a fonte é
  `report/relatorio.tex`.

## Resumo (para quem não é de ML)

- **Problema:** escolher o tema certo de cada questão entre ~375 temas parecidos.
  Se o tema correto nem entrar na lista de opções oferecidas ao modelo, ele pode
  errar mesmo raciocinando bem.
- **Solução:** uma busca textual propõe candidatos; dois modelos votam (4 votos);
  regras consolidam os votos; uma segunda checagem (que vê todos os temas)
  encaminha para revisão quando discorda.
- **Fora da entrega:** melhorar a busca (dicionário + temas "irmãos") elevaria o
  acerto da busca de ~67% para ~95%, mas num A/B **fim-a-fim** esse ganho **não**
  se converteu em decisão (ver `docs/ab_dicionario.md`); ficou como proposta.

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # preencha GEMINI_API_KEY
# coloque questoes.jsonl, temas.csv e entrega_modelo.csv em data/
```

> **Dados.** O banco de questões e os textos derivados **não estão versionados**
> (são dados da empresa; ver `.gitignore`). O avaliador coloca `questoes.jsonl`,
> `temas.csv` e `entrega_modelo.csv` em `data/` e roda **`python -m src.clean`
> antes** do `python -m src.decide`: o `outputs/questoes_limpas.csv` (com o texto)
> é gerado localmente, não vem no pacote.

**Ordem real do pipeline** (o juiz e o `decide` rodam mais de uma vez, porque
ampliar a busca troca os candidatos; o juiz só chama a API nos prompts novos):

```bash
python -m src.clean
python -m src.candidates
python -m src.judge
python -m src.decide
python -m src.expandir_fora            # lê publicacao.csv e o voto 'fora'
python -m src.judge
python -m src.decide
python -m src.fallback_arvore --apply  # lê publicacao.csv e votos.jsonl
python -m src.judge
python -m src.decide
cp publicacao.csv outputs/publicacao_congelada.csv   # baseline do verificador
python -m src.verificar_arvore --rodar               # lê publicacao_congelada.csv
python -m src.decide
python -m src.validate
```

| Artefato | Origem |
|---|---|
| `outputs/questoes_limpas.csv` | `src.clean` |
| `outputs/candidatos.json` | `src.candidates` (ampliado pelo juiz/`expandir_fora`/`fallback_arvore`) |
| `outputs/votos.jsonl`, `outputs/uso.json` | `src.judge` |
| `publicacao.csv`, `outputs/agregado.csv` | `src.decide` |
| `outputs/publicacao_congelada.csv` | cópia do `publicacao.csv` antes do verificador |
| `outputs/votos_verificacao.jsonl` | `src.verificar_arvore --rodar` |

O verificador reaproveita o **mesmo prompt do juiz** (`prompts/judge_prompt.md`), passando a
**árvore inteira** como lista de candidatos (`src/verificar_arvore.py`).

Teste sem custo e sem internet: `JUDGE_BACKEND=mock python -m src.judge`. O mock não é IA, só verifica o fluxo, e grava em `outputs/votos_mock.jsonl` (não toca em `votos.jsonl` nem em `uso.json`).
As chamadas ao modelo ficam em cache (`outputs/cache`). Rodar de novo não gasta de novo.
**Reproduzir sem API** (com os dados em `data/`): `python -m src.clean && python -m src.decide && python -m src.validate`.
O `decide` usa `outputs/questoes_limpas.csv` (a disciplina de origem, para a regra dos gêmeos),
que **não** vem versionado; `outputs/candidatos.json`, `outputs/votos.jsonl` e
`outputs/votos_verificacao.jsonl` **vêm** no repositório.

### Experimentos (não fazem parte da entrega)

Módulos opt-in em `src/experimentos/` (avaliação de recuperação, baselines, A/B do
dicionário, classificador, irmãos/gêmeos, custo, auditoria e congelamento de
métricas), além do `src.contexto_cache` (cache do prefixo repetido). **Nenhum**
entra no `publicacao.csv`; só o pipeline de `src/` gera a entrega. A lista dos
módulos está em [`src/experimentos/README.md`](src/experimentos/README.md).

**Flags opt-in (não mudam a entrega):** `RETRIEVAL_DIC=1` aplica o **dicionário na consulta**
do `src.candidates` (mesma lógica do `+dic` do `src.eval`); `CANDIDATOS_OUT=<arquivo>` grava a
lista em outro lugar; `CONTEXT_CACHE=1` liga o **cache de contexto** no `src.verificar_arvore`
(o bloco da árvore, ~9 mil tokens, é enviado uma vez). Nenhuma dessas flags roda por padrão.

**Melhoria de recuperação (offline, validada em dev/holdout).** Dois ganhos que se somam:
o **dicionário jurídico** (`data/dicionario_juridico.csv`) e a **expansão por irmãos**.
`recall_hier` @ k=10 passa de **0,667** (config atual) para **0,957**; Legislação Especial
de **5/19** para **16/19**. Numa **segunda rotulagem independente** (`data/rotulos_opus.tsv`,
150 questões) o mesmo padrão se mantém: 0,791 → **0,973**, Legislação Especial 16/28 → **25/28**
(`docs/rotulos_opus.md`). Detalhes e ressalvas: `docs/avaliacao.md`, `docs/dicionario_juridico.md`
e `docs/irmaos_comparativo.md`. **Ainda não foi adotado no `publicacao.csv`** (mudar o prompt
invalida o cache do juiz).

> **Aviso (testado fim-a-fim).** Um A/B **pago** no nível da decisão (Opus 148,
> **quase fora da amostra**: 41 já no conjunto de desenho)
> mostrou que esse ganho de **busca** quase **não** chega à **decisão**: com o dicionário,
> `recall_hier` sobe 0,791 → 0,845, mas a concordância das publicadas muda **+0,2 pp** (1
> questão): os acertos extras caem em `revisar`, que a métrica não conta. Decomposição:
> `docs/ab_dicionario.md`.

## Como a classificação funciona

1. **Limpeza:** remove HTML e junta enunciado, comando e alternativas.
2. **Candidatos:** TF-IDF pega os 10 temas mais próximos, mais os pais desses temas
   e os filhos dos 3 primeiros. Temas inativos e raízes (disciplinas) ficam de
   fora. O `assunto_origem` entra só como pista de texto.
3. **Juiz:** o LLM escolhe um candidato (ou `fora`), com confiança e motivo, em 4
   votos (`gemini-3.6-flash` e `gemini-3.1-flash-lite`).
4. **Decisão** (`src/decide.py`):
   - votos iguais: publica no tema, se a confiança passar do limiar;
   - votos em subtemas do mesmo ramo: publica no **tema pai** (a régua aceita pai e filho);
   - votos em temas diferentes: `revisar`, com o tema mais votado como sugestão;
   - metade ou mais dos votos em `fora`: `fora`;
   - temas "lixeira" (muitas questões na origem) exigem confiança extra.
5. **Verificador:** um 5º voto, do `flash-lite` com a **árvore inteira**. Se ele
   discorda do tema publicado, a questão vai para revisão. Motivo: os erros eram
   unânimes por falha de recuperação; só uma recuperação diferente os pega.
6. **Gêmeos:** temas de mesmo título em disciplinas diferentes só publicam se a
   disciplina de origem conferir com a raiz do tema escolhido. **Por quê:** publicar
   no tema errado é o erro mais caro (o aluno estudaria o tópico errado); na dúvida
   entre gêmeos, rebaixar para revisão é a aposta segura. Custo da premissa: **24
   questões** rebaixadas (~6,7 pontos de cobertura).

## Como estimei a precisão sem gabarito

1. **Amostra estratificada por risco:** grupo A (publicadas só após o fallback) é
   censo; grupo B é amostra aleatória. Rótulo produzido por IA (DeepSeek), a partir
   do texto da questão e da lista de temas.
2. **Denominador correto:** a concordância usa **apenas** as publicadas. As
   rotuladas hoje em `revisar`/`fora` são diagnóstico de cobertura.
3. **Régua do case:** acerto = tema atribuído, pai ou filho direto. Irmãos = erro.
4. **Intervalo de Wilson 95%** sobre a concordância observada.
5. **Transparência:** os rótulos vêm de outro LLM (DeepSeek); mede-se
   **concordância**, não precisão. Ver `docs/transparencia_rotulos.md`.
6. **Segunda rotulagem (Opus) e adjudicação:** uma rotulagem nova de **150 questões**
   (41 em comum com a primeira) dá **0,54 no tema exato** e **0,85 com pai e filho**:
   a concordância depende de quem rotula. Os 6 desacordos foram adjudicados à mão em
   `docs/adjudicacao_erros.csv` (1 rótulo, 1 modelo, 4 ambíguos).

## Resultado desta execução

| Etapa | Publicadas | Concordância observada |
|---|---|---|
| Pipeline base | 261 (72,7%) | 0,838 (57/68) |
| Após o verificador | **222 (61,8%)** | **0,90 (54/60)** |

O verificador concordou em 225 e discordou em 36 das 261; 39 foram rebaixadas (36
discordâncias + 3 por re-agregação). Ele vetou 5 dos 11 erros conhecidos e 3
questões certas (falsos vetos). Auditoria: `docs/auditoria_verificador.md`. O
baseline segue em `outputs/publicacao_congelada.csv`.

`previsao.txt`: precisão **0,86 (0,74 a 0,94)**, cobertura 0,62, revisada após a
segunda rotulagem. O 0,90 é a concordância observada, **não** a previsão.

> `previsao.txt` foi escrito **à mão** nesta entrega. O `src.estimate previsao` mantém o
> método antigo por grupos e grava em `previsao_automatica.txt` (não sobrescreve o entregue).

## Modelos, custo e tempo

Valores de `outputs/uso.json` (execução real; **parciais**; ver escopo no arquivo).

| Item | Valor |
|---|---|
| Modelos do juiz | `gemini-3.6-flash`, `gemini-3.1-flash-lite` |
| Rodadas por modelo | 2 (4 votos por questão) |
| Embeddings (pipeline) | `tfidf` (lexical, sem custo) |
| Tokens de entrada / saída (último run do juiz) | 945.992 / 9.188 (+30.660 de raciocínio) |
| Chamadas novas / cache | 112 / 1.324 |
| Erros de provedor | 4 (inclui Q0227, `PROHIBITED_CONTENT`) |
| Verificação | 261 votos; 246 chamadas novas; **~2,14 M de entrada + ~18 mil de saída lidos no console**, não gravados em arquivo |

O `src/judge.py` grava `uso.json` a cada run (só o último fica) e as etapas
instrumentadas registram em `outputs/uso_etapas.jsonl`. **Medido em arquivo:** o último run
do juiz (≈0,9 M, o fallback) e o A/B do dicionário (≈0,9 M). **Lido no console (`J.STATS`),
não gravado:** o verificador (~2,14 M de entrada + ~18 mil de saída em 246 chamadas).
**Estimado:** o juiz base (≈1,5 mil tok/chamada). Somando: **~5,2 M tokens de entrada →
~US$ 2,1** (**~14,4 M por 1.000 questões**).

Custo por questão: **entre ~US$ 0,006** (piso, só tokens de entrada) **e ~R$ 0,09** (teto
observado: R$ 32,98 de painel ÷ 359, incluindo os experimentos). Para 50 mil por semana:
**entre ~US$ 290 (piso) e ~R$ 4,6 mil (teto)**.

### Tempo

Rodadas do juiz cronometradas: **28, 88, 89 e 25 s** (a de 89,1 s está em
`outputs/uso.json`). A rodada inicial do juiz não foi cronometrada, e a verificação
(261 votos, com a árvore inteira em cada chamada) não registrou segundos; pela taxa
do juiz (~112 chamadas novas em 89 s), a ordem é de **~3 a 4 min**. A máquina, no
total, roda em **minutos**, não em horas; o gargalo foi o **esforço humano** (desenho
do pipeline, adjudicação dos erros conferidos à mão e escrita do relatório), da ordem
de **alguns dias de trabalho** (não cronometrado).

## Decisões tomadas à mão

Veja `docs/decisoes_manuais.md`.

## Estrutura

```
src/        núcleo do pipeline (clean, candidates, expandir_fora, fallback_arvore,
            judge, verificar_arvore, decide, validate) + apoio (eval, recuperacao,
            dicionario, contexto_cache, uso, estimate)
src/experimentos/  módulos de experimentação, opt-in (ab_juiz, ab_dic, experimento_irmaos,
            avaliacao_pipeline, classificador, baseline_svm, audit, seletiva,
            recall_recuperacao, snapshot_metricas, custo); ver o README da pasta
data/       copie dos anexos do case: questoes.jsonl, temas.csv e entrega_modelo.csv
            (não versionados); dicionario_juridico.csv e rotulos_opus.tsv vêm no repo
prompts/    prompt do juiz
report/     relatorio.tex (fonte, Overleaf/pdfLaTeX) e relatorio.pdf (5 páginas, memo
            ao professor na última página)
docs/       decisões manuais, metodologia, transparência, auditoria do verificador,
            adjudicação dos erros, A/B do dicionário
outputs/    artefatos intermediários (votos, agregado, uso, candidatos, experimentos)
```

## O que faria com mais tempo

- **Melhorar o retrieval** (dicionário + irmãos): testado offline, `recall_hier` de 0,667 →
  **0,957** (Legislação Especial 5/19 → 16/19). Muda o prompt do juiz e invalida o cache:
  precisa re-julgar. O dicionário sozinho (lista pequena) já entrega o essencial por
  **menos**; irmãos custam ~6× de lista por ganho marginal e expõem a confusão por **gêmeo**
  (exposição 4 → 10). Análise: `docs/irmaos_comparativo.md`.
- **Embeddings densos** com modelo grande/ajustado ao domínio jurídico; no teste
  offline, um `e5-large` local empatou, mas **não superou** o TF-IDF + irmãos.
- Coletar **rótulos de especialistas** (não-LLM) para medir precisão de verdade e
  treinar um classificador depois.
- Rodadas com modelos de **famílias diferentes** e mais anotadores.
- Confirmar com a organização a convenção dos temas **gêmeos**.
- Consolidar **uso/custo** acumulado de todas as etapas (hoje o `uso.json` guarda só o
  último run do juiz).
- **Com o professor no circuito** (itens 6–8 do relatório): ligações curadas lei→tema e
  entre **gêmeos**, validadas por ele; **regra de decisão por custo**, quando houver
  probabilidade calibrada; **aprendizado ativo** (a revisão dele gera rótulos e treina o
  classificador).

> No relatório (Seção c), a mesma lista aparece agrupada em **8 itens**.
