# Proveniência: artigos_tema.csv

- **O que é:** tabela de faixas de artigos do Código Penal (Decreto-Lei 2.848/1940) e do Código de
  Processo Penal (Decreto-Lei 3.689/1941) para temas do `temas.csv` do case.
- **Quem propôs:** Claude (Anthropic), em 21/10/2026, a partir da estrutura dos dois códigos (títulos,
  capítulos e artigos) e da lista de temas ativos do catálogo.
- **Status:** PROPOSTA, NÃO REVISADA. Precisa ser conferida contra o índice oficial dos códigos antes de
  qualquer uso na decisão. Pontos de atenção: artigos inseridos por leis recentes (sufixos -A, -B...),
  artigos revogados e faixas em que um capítulo cobre vários subtemas.
- **Regra de uso:** um artigo com sufixo (ex.: 121-A) casa só com a linha que tem o mesmo sufixo; um
  artigo sem sufixo casa com a faixa numérica que o contém.
- **O que não está:** Livro IV do CPP (execução, arts. 668 a 779), porque o catálogo tem dois temas
  gêmeos de execução (4703 e 6734) e a convenção da equipe não está clara para o CPP; e a rixa (art. 137
  do CP), que não tem tema próprio.
- **Uso pretendido:** sinal de evidência objetiva, independente da similaridade de texto, para o
  experimento da rodada 2. Nunca chama modelo de linguagem na hora de classificar.

# Proveniência: leis_tema.csv

- **O que é:** número de lei especial para o tema de Legislação Especial do catálogo (sempre o gêmeo 47xx,
  que a folha-verdade indica como o preferido da equipe em 5 de 6 casos).
- **Quem propôs:** Claude (Anthropic), em 21/10/2026. **Status:** proposta, a conferir.
- **Teste exploratório já feito (desenhado depois de ver os erros):** nas 9 questões da folha que citam
  exatamente uma lei especial, a lei aponta um tema aceito pela régua em 8; o modelo, em 4.
- **Teste exploratório dos artigos (mesmo dia):** nas 7 questões da folha com um único ramo indicado por
  artigo do CP ou CPP, o artigo acertou 4 e o modelo 4. Os 4 acertos do artigo vieram da Parte Geral do CP
  (arts. 1 a 120); os 3 erros vieram da Parte Especial, em que o artigo citado descreve o cenário da questão
  e não o assunto cobrado (ex.: Q0202 cita o estupro e cobra erro de tipo). Hipótese para a rodada 2:
  usar só artigos da Parte Geral do CP e do CPP.
