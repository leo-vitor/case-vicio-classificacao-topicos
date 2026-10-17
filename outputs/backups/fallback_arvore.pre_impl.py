"""Etapa 2c: fallback com a arvore inteira.
Quando algum voto disse 'fora' e a questao nao foi publicada, o juiz recebe todos os temas (sem busca)."""
import json
import os

import pandas as pd

from src.config import OUT, ROOT
from src.temas import Arvore


def main():
    arv = Arvore()
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    nao_pub = set(pub.loc[pub["decisao"] != "publicar", "id"])
    ids = []
    with open(OUT / "votos.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] in nao_pub and any(v["fora"] for v in r["votes"]):
                ids.append(r["id"])
    so = os.getenv("FALLBACK_IDS")
    if so:
        ids = [i for i in ids if i in set(so.split(","))]
    todos = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    cand = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    for qid in ids:
        cand[qid]["candidatos"] = todos
    (OUT / "candidatos.json").write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")
    chars = sum(len(arv.caminho[t]) + 8 for t in todos)
    print(f"{len(ids)} questoes com a arvore inteira ({len(todos)} temas, ~{chars // 3} tokens por prompt).")
    print(sorted(ids))


if __name__ == "__main__":
    main()