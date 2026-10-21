"""Ajustes de taxonomia da Fase 2 (v02), aplicados no carregamento da arvore.

`data/temas.csv` e insumo do case e nao sobe no git. Para que a correcao
sobreviva a um download novo, ela vive aqui e e aplicada de forma idempotente
por `Arvore`. Ver `docs/decisoes.md`, secao 12.

O que muda:

- 5148 "Dos Crimes contra as Instituicoes Democraticas" (Capitulo II do Titulo
  XII do CP) passa a ser filho de 5155;
- 5156 "Dos Crimes contra o Funcionamento dos Servicos Essenciais" (Capitulo IV
  do Titulo XII, art. 359-R) passa a ser filho de 5155;
- 5155 permanece nivel 1, agora como o Titulo XII que e.
"""
PAI = "5155"

# id -> (titulo, n de questoes no source)
FILHOS = {
    "5148": ("Dos Crimes contra as Instituições Democráticas", 3),
    "5156": ("Dos Crimes contra o Funcionamento dos Serviços Essenciais", 5),
}


def aplicar(df):
    """Reescreve pai, nivel, caminho e descricao dos tres nos. Idempotente."""
    if PAI not in set(df["tema_id"]):
        return df
    df = df.copy()
    titulo_pai = df.loc[df["tema_id"] == PAI, "titulo"].iloc[0]
    for tid, (titulo, nq) in FILHOS.items():
        m = df["tema_id"] == tid
        if not m.any():
            continue
        df.loc[m, "parent_id"] = PAI
        df.loc[m, "nivel"] = "2"
        df.loc[m, "caminho"] = f"Penal > {titulo_pai} > {titulo}"
        df.loc[m, "descricao"] = (
            f"Subtema de '{titulo_pai}' (Penal). {nq} questões no source. "
            f"Path: Penal > '{titulo_pai}' > '{titulo}'."
        )
    return df
