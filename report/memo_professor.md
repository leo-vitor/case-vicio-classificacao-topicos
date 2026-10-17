# Memo para o professor (1 página)

> **Integrado ao relatório.** Este memo é a seção (d) de `report/relatorio.tex` (página final
> do PDF). Este `.md` é mantido só como rascunho.

> **Resultado em três linhas**
> - **Operação:** 222 questões publicadas (61,8% das 359), 136 para revisão, 1 fora do escopo.
> - **Qualidade:** 54 acordos em 60 questões avaliadas — **90% de concordância** (limite inferior ~80%).
> - **Limitação:** os rótulos de referência vêm de IA; por isso **não** confirmam a meta de 95%.

**O que encontrei**

- O sistema acerta bem quando o tema é claro; dos 11 erros publicados, só 3 são de
  **legislação especial de Penal e Processo Penal**, e alguns vêm de questões com
  assertivas I–IV, em que o enunciado dá pouca pista lexical.
- Em vários erros, o tema certo **não chegava nem a ser oferecido** ao modelo: ele
  escolhia o melhor entre opções que não incluíam a resposta. É um problema de
  **busca**, não de conhecimento jurídico. Quando a busca oferece o tema certo, o
  modelo raramente erra.
- O erro é **confiante**: nas questões erradas, os dois modelos concordaram por
  unanimidade. Por isso adicionei uma **verificação** com a árvore inteira, que
  encaminha para revisão as questões em que esse 5º voto discorda. Isso reduziu a
  lista publicada de 261 para 222 itens.
- O catálogo tem armadilhas: **temas com o mesmo nome em disciplinas diferentes**
  (8 pares) e temas que se sobrepõem (pai e filho dizendo coisas parecidas). Nesses
  casos prefiro **não publicar** a arriscar o par errado.

**O que já consegui melhorar (offline, sem tocar na entrega)**

- Ataquei o ponto fraco (**legislação especial**) com um **dicionário jurídico**
  (traduz o número da lei para o apelido do tema, ex.: "Lei 11.340" → "Lei Maria da
  Penha") somado à expansão por temas **irmãos**: a busca passou a achar o tema (ou
  um relacionado) em **0,957** dos casos, contra **0,667** hoje, e em legislação
  especial de **5/19** para **16/19**. O ganho se mantém no holdout (0,968), com a
  ressalva de que a última expansão foi guiada pelos erros observados. A parte local
  é **grátis**.
- **Levei o dicionário até a decisão** (teste fim-a-fim, pago, numa rotulagem
  independente de 148 questões): ele **sobe a busca** (recall +5,4 pp) mas muda a
  publicação em apenas **+0,2 pp** (1 questão) — a maior parte do ganho cai em
  **revisão**, não em publicação. Por isso **não adotei** o dicionário na entrega.
- Refiz os testes numa **segunda rotulagem independente** (150 questões, outro
  modelo): o resultado **se reproduz** (0,92 de concordância) e **não observei erro
  por escolha de gêmeo** (poucos casos; a convenção de título duplicado **não está
  confirmada**), mas o acordo entre as duas rotulagens é de só **0,54** no tema
  exato (0,85 no ramo) — o número **depende de quem rotula**.

**O que recomendo mudar nos temas**

- Dar nomes que **distingam** os gêmeos (ex.: citar a disciplina no título).
- Fundir ou hierarquizar melhor os subtemas que repetem o conteúdo do pai.
- Marcar quais temas são "guarda-chuva" (onde aceitar o nível mais geral é seguro)
  e quais exigem o nível mais específico.
- Aproximar, na árvore, os temas de **legislação especial** que hoje ficam
  distantes dos institutos correspondentes do Código.

**O que preciso de você**

- Uma **amostra rotulada por professor** (mesmo ~100 questões) para eu medir a
  precisão **de verdade**. Hoje minha referência é assistida por IA e só mede
  concordância: observo **90% de concordância** em 60 publicadas, mas isso **não**
  permite afirmar que a precisão real seja de pelo menos 95%.
- Confirmação da convenção dos **temas gêmeos** no gabarito.
- Um parecer sobre **6 casos** específicos (`docs/adjudicacao_erros.csv`), hoje
  marcados como ambíguos ou prováveis, para eu fechar a avaliação.
- Prioridade entre **publicar mais** (mais cobertura, mais risco) e **publicar só
  o que é seguro** (menos cobertura). Nesta entrega escolhi o segundo caminho.

**Como formulo o resultado (sugestão de texto)**

> A solução prioriza a precisão por meio de votação, recuperação ampliada,
> verificação e encaminhamento de casos discordantes para revisão. A avaliação
> preliminar observou 90% de concordância em 60 questões publicadas, mas não
> permite afirmar que a precisão real seja de pelo menos 95%, pois a amostra é
> pequena e os rótulos de referência não foram validados independentemente por
> especialistas.
