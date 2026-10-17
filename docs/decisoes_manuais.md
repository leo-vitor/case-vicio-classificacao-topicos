# Decisões tomadas à mão

Registre aqui tudo que não veio do pipeline. Uma linha por decisão.

| O que fiz | Onde | Por quê |
|---|---|---|
| Rotulei 93 questões da amostra, às cegas (80 iniciais + 13 do censo do grupo A) | `outputs/amostra_rotulagem.csv` | Não há gabarito; preciso estimar concordância sem ver a saída do modelo |
| Excluí raízes (nível 0) da lista de candidatos | `src/candidates.py` | Publicar na disciplina inteira não ajuda o aluno |
| Adotei a régua pai/filho (irmãos = erro) | `src/estimate.py` | É a métrica declarada no case |
| Separei a amostra em grupos A (censo) e B (amostra) | `src/estimate.py` | O fallback mexeu nas questões difíceis; o censo do grupo A reduz o viés |
| Mantive o fallback com a árvore inteira, mas tornei-o reversível | `src/fallback_arvore.py` | Mudar `candidatos.json` sem backup é irreversível |
| Adotei o **verificador** (5º voto, árvore inteira, `flash-lite`) como controle das publicadas | `src/verificar_arvore.py`, `src/decide.py` | Os erros eram unânimes por falha de busca; a árvore inteira enxerga todos os temas |
| Não promovi `revisar → publicar` | `src/decide.py` | Promover aumenta cobertura às custas de precisão |
| Mantive os temas gêmeos em `revisar` | `src/decide.py` | Convenção de título duplicado não confirmada pela organização |
| Deixei Q0227 em revisão (`PROHIBITED_CONTENT`) | `outputs/votos.jsonl` | Bloqueio do provedor; não forcei o modelo |
| **Não** usei a política seletiva do DeepSeek na entrega; deixei `src/seletiva.py` como experimento isolado | `src/seletiva.py` | Ela publicava 95 questões apoiada em ~17 rótulos; o número era frágil e calibrado na mesma amostra |
| Registrei a adjudicação dos 6 desacordos com grau de certeza, sem fixar verdade jurídica | `docs/adjudicacao_erros.csv` | Evitar transformar avaliação incerta em gabarito |
| Escrevi o `previsao.txt` à mão, separando concordância observada de precisão real | `previsao.txt` | A precisão real, sem especialista, permanece desconhecida |
| Testei a expansão por irmãos offline e deixei como recomendação, sem alterar a entrega | `src/recall_recuperacao.py` | Funciona para recall, mas mexer nos candidatos invalida o cache do juiz (custo) e não foi validado fim-a-fim |
| Congelei as métricas atuais (hashes, decisões, concordância) antes do A/B | `src/snapshot_metricas.py`, `outputs/experimentos/baseline_snapshot/` | Ter uma base versionada e comparável para decidir se vale gastar créditos |
| Rodei um A/B **pago** do dicionário no retrieval (Opus 148, out-of-sample) | `src/ab_juiz.py`, `src/ab_dic.py`, `docs/ab_dicionario.md` | O dicionário sobe o recall (+5,4 pp) mas **não move a decisão** (+1 publicada); o ganho cai em `revisar`. **Não adotado** na entrega |
| Liguei o **cache de contexto** no verificador como recomendação de produção | `src/contexto_cache.py`, `CONTEXT_CACHE=1` em `src/verificar_arvore.py` | Num teste pequeno, ~98% dos tokens de entrada vieram do cache, com a mesma qualidade; a **saída não foi guardada** e não reexecutei (créditos de API esgotados). O desconto em preço **não** foi confirmado. Plano e reprodutibilidade: `docs/cache_contexto.md` |

## Notas

- Os rótulos foram produzidos com assistência de IA (**DeepSeek**). Ver
  `docs/transparencia_rotulos.md`.
- A avaliação e os números completos estão em `docs/metodologia_avaliacao.md`.
- A auditoria do verificador está em `docs/auditoria_verificador.md`.
