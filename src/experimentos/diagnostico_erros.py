"""Diagnostico dos erros das publicadas (baseline congelado) contra os rotulos da amostra.

Uso, da raiz do repositorio:
  python -m src.experimentos.diagnostico_erros                 (baseline: outputs/publicacao_congelada.csv)
  python -m src.experimentos.diagnostico_erros publicacao.csv  (qualquer outro arquivo de publicacao)

Se existir docs/adjudicacao_erros.csv (colunas: id, veredito, motivo; veredito = modelo | ambos | rotulo | nao_sei),
calcula tambem a precisao ajustada pela sua adjudicacao.
"""
import json
import sys
from math import sqrt
from pathlib import Path

import pandas as pd

from src.config import OUT, ROOT
from src.temas import Arvore

MAPA = {"Direito Penal": "Penal", "Direito Processual Penal": "Processo Penal"}


def wilson_inf(k, n, z=1.96):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def main():
    a = Arvore()
    raiz = lambda t: a.caminho.get(t, "").split(" > ")[0]

    rot = pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")
    rot = rot[rot["tema_correto_id"] != ""][["id", "tema_correto_id", "incerto"]]
    PUB = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "publicacao_congelada.csv"
    pub = pd.read_csv(PUB, dtype=str).fillna("")[["id", "decisao", "tema_central_id"]]
    ag = pd.read_csv(OUT / "agregado.csv", dtype=str).fillna("")[["id", "kind", "nq"]]
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")[["id", "texto", "disciplina_origem"]]
    q = q.rename(columns={"texto": "texto_full"})
    cand = json.load(open(OUT / "candidatos.json", encoding="utf-8"))

    t = a.ativos[a.ativos.nivel >= 1]
    gem = set(t.groupby("titulo").filter(lambda g: g.caminho.str.split(" > ").str[0].nunique() > 1).tema_id)

    df = rot.merge(pub, on="id").merge(ag, on="id").merge(q, on="id")
    df = df[df["decisao"] == "publicar"].copy()
    df["certo"] = [a.relacionado(r.tema_central_id, r.tema_correto_id) for r in df.itertuples()]
    df["oferecido"] = [any(a.relacionado(r.tema_correto_id, c) for c in cand[r.id]["candidatos"]) for r in df.itertuples()]
    df["gemeo"] = df["tema_central_id"].isin(gem)
    df["lixeira"] = df["nq"].astype(float) >= 40
    df["origem_bate"] = [raiz(r.tema_central_id) == MAPA.get(r.disciplina_origem, r.disciplina_origem) for r in df.itertuples()]
    df["nivel"] = df["tema_central_id"].map(a.nivel)

    n, k = len(df), int(df["certo"].sum())
    if n == 0:
        sys.exit("Nenhuma questao publicada e rotulada neste arquivo.")
    print(f"Arquivo: {PUB}")
    print(f"Publicadas rotuladas: {n} | certas: {k} ({k / n:.2f}) | limite inferior Wilson: {wilson_inf(k, n):.2f}")
    print("ATENCAO: rotulos feitos com ajuda do DeepSeek; isto mede concordancia, nao precisao contra especialistas.")

    for col in ["kind", "gemeo", "lixeira", "origem_bate", "oferecido", "nivel"]:
        g = df.groupby(col)["certo"].agg(["size", "sum"])
        g["erros"] = g["size"] - g["sum"]
        g["taxa_erro"] = (g["erros"] / g["size"]).round(2)
        print(f"\n{col}")
        print(g[["size", "erros", "taxa_erro"]].to_string())

    err = df[~df["certo"]]
    print(f"\n=== {len(err)} ERROS PARA ADJUDICAR ===")
    for r in err.itertuples():
        print(f"\n{r.id} | kind: {r.kind} | oferecido: {r.oferecido} | gemeo: {r.gemeo} | incerto: {r.incerto}")
        print("  MODELO :", a.caminho.get(r.tema_central_id, "?"))
        print("  ROTULO :", a.caminho.get(r.tema_correto_id, "?"))
        print("  TEXTO  :", " ".join(r.texto_full.split())[:350])

    adj_path = ROOT / "docs" / "adjudicacao_erros.csv"
    if adj_path.exists():
        adj = pd.read_csv(adj_path, dtype=str).fillna("")
        v = adj.set_index("id")["veredito"]
        flip = sum(1 for i in err["id"] if v.get(i, "") in ("modelo", "ambos"))
        k2 = k + flip
        print(f"\nAdjudicacao: {len(adj)} veredictos | erros revertidos (modelo/ambos): {flip}")
        print(f"Precisao ajustada: {k2}/{n} = {k2 / n:.2f} | limite inferior Wilson: {wilson_inf(k2, n):.2f}")
        print("Ressalva: so os desacordos foram revistos, por nao especialista; trate como estimativa otimista.")


if __name__ == "__main__":
    main()
