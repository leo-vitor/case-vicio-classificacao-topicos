"""Confere o publicacao.csv contra as regras do LEIA-ME antes de enviar."""
import sys
from pathlib import Path

import pandas as pd

from src.clean import load_questoes
from src.config import ROOT
from src.temas import Arvore


def main(path=None):
    path = Path(path or ROOT / "publicacao.csv")
    arv = Arvore()
    ids = [q["id"] for q in load_questoes()]
    df = pd.read_csv(path, dtype=str).fillna("")
    erros = []
    if list(df.columns) != ["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"]:
        erros.append(f"colunas inesperadas: {list(df.columns)}")
    if len(df) != len(ids) or set(df["id"]) != set(ids) or df["id"].duplicated().any():
        erros.append(f"ids nao batem: {len(df)} linhas, esperado {len(ids)} unicos")
    for r in df.itertuples():
        if r.decisao not in ("publicar", "revisar", "fora"):
            erros.append(f"{r.id}: decisao invalida '{r.decisao}'")
            continue
        if r.decisao == "fora" and r.tema_central_id:
            erros.append(f"{r.id}: fora deve ter tema vazio")
        if r.decisao != "fora":
            if not r.tema_central_id or r.tema_central_id not in arv.ativo:
                erros.append(f"{r.id}: tema_central_id ausente ou inativo '{r.tema_central_id}'")
        if r.decisao in ("revisar", "fora") and not r.motivo.strip():
            erros.append(f"{r.id}: motivo obrigatorio")
        try:
            if not 0 <= float(r.confianca) <= 1:
                erros.append(f"{r.id}: confianca fora de 0-1")
        except ValueError:
            erros.append(f"{r.id}: confianca invalida")
        for e in [x for x in r.extras_ids.split(";") if x]:
            if e not in arv.ativo:
                erros.append(f"{r.id}: extra invalido '{e}'")
    if erros:
        print(f"{len(erros)} problema(s):")
        print("\n".join(erros[:30]))
        sys.exit(1)
    print(f"OK: {len(df)} linhas validas.", df["decisao"].value_counts().to_dict())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
