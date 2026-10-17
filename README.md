# Case Vício (Método VDE): classificação de tópicos

Pipeline que decide, para cada uma das 359 questões, entre **publicar**,
**revisar** e **fora**, com votação de LLM, recuperação ampliada, verificação e
uma avaliação de precisão **sem gabarito**.

Entrega: `publicacao.csv` (raiz) e `previsao.txt`.

> **O que a avaliação permite afirmar.** Observamos **90% de concordância**
> (54/60) nas questões publicadas, com limite inferior de Wilson ~80%. Isso **não**
> é precisão contra especialistas: os rótulos foram produzidos com assistência de
> outro LLM (DeepSeek). Não afirmamos que a meta de 95% foi atingida. Detalhes em
> `docs/metodologia_avaliacao.md` e `docs/transparencia_rotulos.md`.

## Resumo (para quem não é de ML)

- **Problema:** escolher o tema certo de cada questão entre ~375 temas parecidos.
  Se o tema correto nem entrar na lista de opções oferecidas ao modelo, ele pode
  errar mesmo raciocinando bem.
- **Solução:** uma busca textual propõe candidatos; dois modelos votam (4 votos);
  regras consolidam os votos; uma segunda checagem (que vê todos os temas)
  encaminha para revisão quando discorda.
- **Resultado:** **222 publicadas** (61,8%), **136 para revisão**, **1 fora do
  escopo**. A decisão de publicar menos reduz o risco, mas **não comprova** 95% de
  precisão.
- **Qualidade:** **90% de concordância** (54 de 60 avaliadas). Como os rótulos de
  referência foram feitos com apoio de IA, a **precisão real permanece
  desconhecida**.
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
> antes** do `python -m src.decide` — o `outputs/questoes_limpas.csv` (com o texto)
> é gerado localmente, não vem no pacote.

| Passo | Comando | Gera |
|---|---|---|
| 1. Limpeza do HTML | `python -m src.clean` | `outputs/questoes_limpas.csv` |
| 2. Temas candidatos | `python -m src.candidates` | `outputs/candidatos.json` |
| 2b. Ampliar busca dos `fora` | `python -m src.expandir_fora` | amplia candidatos dos casos com voto `fora` |
| 2c. Fallback (árvore inteira) | `python -m src.fallback_arvore --apply` | sobrescreve `candidatos.json` (com backup) |
| 3. Juiz (LLM, várias rodadas) | `python -m src.judge` | `outputs/votos.jsonl`, `outputs/uso.json` |
| 4a. Verificador (5º voto) | `python -m src.verificar_arvore --rodar` | `outputs/votos_verificacao.jsonl` |
| 4b. Regras de decisão | `python -m src.decide` | `publicacao.csv`, `outputs/agregado.csv` |
| 5. Validar formato | `python -m src.validate [arquivo]` | confere o `publicacao.csv` |

Teste sem custo e sem internet: `JUDGE_BACKEND=mock python -m src.judge`. O mock não é IA, só verifica o fluxo.
As chamadas ao modelo ficam em cache (`outputs/cache`). Rodar de novo não gasta de novo.
Reproduzir sem API: `python -m src.decide` + `python -m src.validate`.

### Experimentos (não fazem parte da entrega)

- `python -m src.eval --split` / `--sweep` / `--config tfidf+irmao+dic --k 10` —
  avaliação **canônica** de recuperação (métricas, IDs de erro, versão dos dados).
  Ver `docs/avaliacao.md`.
- `python -m src.experimentos.recall_recuperacao` — experimento histórico de recuperação (TF-IDF/BM25/
  denso/RRF + expansões). Superado por `src.eval`, mantido por rastreabilidade.
- `python -m src.experimentos.audit recall|erros|votos|latente` — auditoria offline.
- `python -m src.experimentos.baseline_svm` — baseline supervisionado (TF-IDF + SVM linear).
- `python -m src.experimentos.custo` — consumo por etapa e projeção por 1.000/50.000 questões.
- `python -m src.experimentos.experimento_irmaos` — irmãos × risco de **gêmeo** × custo (offline, grátis).
  Ver `docs/irmaos_comparativo.md`.
- `python -m src.experimentos.ab_juiz --dry-run` / `--rodar` — A/B do juiz entre configs de recuperação
  (dry-run grátis; `--rodar` **gasta API**). Ver `docs/irmaos_comparativo.md`.
- `python -m src.experimentos.avaliacao_pipeline --rotulos data/rotulos_opus.tsv` — pipeline congelado ×
  **rotulagem nova** (offline): concordância, gêmeos, por grau de dúvida. Ver `docs/rotulos_opus.md`.
- `python -m src.eval --sweep --rotulos data/rotulos_opus.tsv` (e
  `src.experimentos.experimento_irmaos --rotulos ...`) — mesmos testes numa **rotulagem alternativa**.
- `src/experimentos/seletiva.py` — política seletiva testada e **não adotada** (apoiava-se em ~17 rótulos).
- `python -m src.experimentos.classificador [--rotulos ...] [--cruzado]` — **classificador treinado** offline
  (TF-IDF + regressão logística): validação cruzada, generalização entre rotulagens, calibração
  e **precisão a cobertura fixa**. Piso de comparação; sai em `outputs/experimentos/classificador/`.
- `python -m src.contexto_cache [--dry-run|--criar|--validar]` — **cache de contexto** do prefixo
  repetido (a árvore). `--dry-run` só estima tokens (grátis); `--criar`/`--validar` usam API.
- `python -m src.experimentos.ab_dic [--rotulos ...] [--configs ...] [--par A B]` — **analisa o A/B** já
  pago (votos do `src.experimentos.ab_juiz`): decisão com/sem verificador, Legislação Especial e diferença
  pareada (ganho/perda por questão). Offline. Ver `docs/ab_dicionario.md`.
- `python -m src.experimentos.snapshot_metricas` — congela **todas as métricas atuais** em
  `outputs/experimentos/baseline_snapshot/` (hashes, decisões, concordância, recuperação).

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

> **Aviso (testado fim-a-fim).** Um A/B **pago** no nível da decisão (Opus 148, out-of-sample)
> mostrou que esse ganho de **busca** quase **não** chega à **decisão**: com o dicionário,
> `recall_hier` sobe 0,791 → 0,845, mas a concordância das publicadas muda **+0,2 pp** (1
> questão) — os acertos extras caem em `revisar`, que a métrica não conta. Decomposição:
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
   unânimes por falha de recuperação — só uma recuperação diferente os pega.
6. **Gêmeos:** temas de mesmo título em disciplinas diferentes só publicam se a
   disciplina de origem conferir com a raiz do tema escolhido.

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

## Resultado desta execução

| Etapa | Publicadas | Concordância observada |
|---|---|---|
| Pipeline base | 261 (72,7%) | 0,838 (57/68) |
| Após o verificador | **222 (61,8%)** | **0,90 (54/60)** |

O verificador concordou em 225 e discordou em 36 das 261; 39 foram rebaixadas (36
discordâncias + 3 por re-agregação). Ele vetou 5 dos 11 erros conhecidos e 3
questões certas (falsos vetos). Auditoria: `docs/auditoria_verificador.md`. O
baseline segue em `outputs/publicacao_congelada.csv`.

`previsao.txt`: precisão observada 0,90 (0,80–0,95); cobertura 0,62.

> `previsao.txt` foi escrito **à mão** nesta entrega (o `src.estimate previsao`
> mantém o método antigo por grupos, preservado apenas como histórico).

## Modelos, custo e tempo

Valores de `outputs/uso.json` (execução real; **parciais** — ver escopo no arquivo).

| Item | Valor |
|---|---|
| Modelos do juiz | `gemini-3.6-flash`, `gemini-3.1-flash-lite` |
| Rodadas por modelo | 2 (4 votos por questão) |
| Embeddings (pipeline) | `tfidf` (lexical, sem custo) |
| Tokens de entrada / saída (último run do juiz) | 945.992 / 9.188 (+30.660 de raciocínio) |
| Chamadas novas / cache | 112 / 1.324 |
| Erros de provedor | 4 (inclui Q0227, `PROHIBITED_CONTENT`) |
| Verificação | 261 votos; 246 chamadas novas (~2,14 M de entrada + 18 mil de saída) |

O `src/judge.py` grava `uso.json` a cada run (só o último fica); as demais etapas
registram em `outputs/uso_etapas.jsonl`. Somando as etapas medidas: **~5,2 M tokens de
entrada → ~US$ 2,1** (**~14,4 M por 1.000 questões**) e **~US$ 0,0058 por questão**
(~US$ 5,8 por mil; ~US$ 290 por semana para 50 mil). É um **piso**: conta só tokens de
entrada, sem raciocínio nem saída — a primeira rodada completa consumiu **~R$ 14** no
painel, mais que o US$ 1,04 do juiz na tabela.

### Tempo

Rodadas do juiz cronometradas: **28, 88, 89 e 25 s** (a de 89,1 s está em
`outputs/uso.json`). A rodada inicial do juiz não foi cronometrada, e a verificação
(261 votos, com a árvore inteira em cada chamada) não registrou segundos — pela taxa
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
            recall_recuperacao, snapshot_metricas, custo) — ver o README da pasta
data/       questoes.jsonl, temas.csv, entrega_modelo.csv, dicionario_juridico.csv
prompts/    prompt do juiz
report/     relatório oficial em LaTeX (relatorio.tex, 5 páginas, Overleaf/pdfLaTeX),
            PDF compilado (relatorio.pdf) e memo ao professor integrado como seção (d);
            os .md são rascunho
docs/       decisões manuais, metodologia, transparência, auditoria do verificador,
            adjudicação dos erros, A/B do dicionário
outputs/    artefatos intermediários (votos, agregado, uso, candidatos, experimentos)
```

## O que faria com mais tempo

- **Melhorar o retrieval** (dicionário + irmãos): testado offline, `recall_hier` de 0,667 →
  **0,957** (Legislação Especial 5/19 → 16/19). Muda o prompt do juiz e invalida o cache —
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
