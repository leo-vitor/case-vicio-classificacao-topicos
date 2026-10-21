"""Experimento 1 — recuperacao x decisao, com denominadores explicitos.

Pergunta: o gargalo e a busca (o ramo certo nao aparece) ou a decisao (o ramo
certo aparece e a regra manda para revisao / publica errado)?

O que este modulo garante, porque a tabela anterior era ambigua:

  - cada questao da folha-verdade aparece **exatamente uma vez**;
  - as categorias sao **mutuamente exclusivas** e somam o denominador;
  - a decisao e lida do entregavel (`publicacao.csv`, regra `p_all`) e, em
    paralelo, da regra in-sample (`p_oof`), com os dois denominadores rotulados;
  - as margens (linha x coluna) sao impressas e conferidas por assercao.

Saida: `artefatos/diagnostico.json` + resumo no terminal.

Uso (da pasta fase2/):
    python -m src.diagnostico
"""
import json

import numpy as np
import pandas as pd

from src.artefato import base, tema1
from src.config import ARTEFATOS, ROOT
from src.decisao import RETRIEVERS
from src.protocolo import acerto
from src.recuperacao import ordem_desc

FAIXAS = [("top-1", 1, 1), ("top-2 a 5", 2, 5), ("top-6 a 10", 6, 10), ("fora do top-10", 11, 10**9)]
CATEGORIAS = [
    "publicado e certo",
    "publicado e errado",
    "revisado, top-1 no ramo certo",
    "revisado, ramo certo no top-2 a 10",
    "revisado, ramo ausente do top-10",
]


def faixa(rank):
    for nome, lo, hi in FAIXAS:
        if lo <= rank <= hi:
            return nome
    raise ValueError(rank)


def ramos_aceitos(arv, gold, qid):
    if gold.loc[qid, "fora"]:
        return set()
    return {r for r in (tema1(arv, t) for t in gold.loc[qid, "alvos"]) if r}


def primeiro_rank(arv, pool, linha, aceitos):
    """Posicao (1-based) do primeiro item cujo ramo esta entre os aceitos."""
    for pos, j in enumerate(ordem_desc(linha), start=1):
        if tema1(arv, pool[int(j)]) in aceitos:
            return pos
    return None


def main():
    b = base()
    arv, gold, ids = b["arv"], b["gold"], b["ids"]
    pool, M = b["pool"], b["M"]
    regra = json.loads((ARTEFATOS / "decisao_resumo.json").read_text(encoding="utf-8"))["regra"]
    tau, cons_min = float(regra["tau"]), float(regra["consenso_min"])

    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).set_index("id")
    dec_csv = dict(zip(pub.index, pub["decisao"]))
    dec_oof = {qid: ("publicar" if (b["cons"][k] >= cons_min and b["p_oof"][k] >= tau) else "revisar")
               for k, qid in enumerate(ids)}

    validos = [qid for qid in ids if not gold.loc[qid, "fora"]]
    fora = [qid for qid in ids if gold.loc[qid, "fora"]]

    # --- uma linha por questao, com rank e decisao -------------------------
    linhas = []
    for qid in ids:
        k = ids.index(qid)
        aceitos = ramos_aceitos(arv, gold, qid)
        rk = None if not aceitos else primeiro_rank(arv, pool, M[k], aceitos)
        linhas.append({
            "id": qid,
            "fora": bool(gold.loc[qid, "fora"]),
            "disciplina": gold.loc[qid, "disciplina"],
            "ramo_previsto": b["pred"][k],
            "ramo_aceitos": sorted(aceitos),
            "rank_ramo": rk,
            "acerto": bool(b["y"][k]),
            "decisao_csv": dec_csv[qid],
            "decisao_oof": dec_oof[qid],
            "p_oof": round(float(b["p_oof"][k]), 6),
            "consenso": round(float(b["cons"][k]), 3),
        })

    # --- assercoes de integridade ------------------------------------------
    assert len(linhas) == len(ids) == len({r["id"] for r in linhas}), "id repetido ou faltando"
    assert sum(1 for r in linhas if r["fora"]) == len(fora) == 8, "fora != 8"
    assert len(validos) == 92, len(validos)
    assert all((r["rank_ramo"] is not None) for r in linhas if not r["fora"]), "rank None em valida"

    # --- crosstab rank x decisao (92 validas), com margens ----------------
    tab = pd.DataFrame(0, index=[f[0] for f in FAIXAS], columns=["publicar", "revisar"], dtype=int)
    for r in linhas:
        if r["fora"]:
            continue
        tab.loc[faixa(r["rank_ramo"]), r["decisao_csv"]] += 1
    assert int(tab.values.sum()) == len(validos) == 92, "crosstab nao soma 92"

    # --- categorias mutuamente exclusivas (92 validas) --------------------
    cats = {c: 0 for c in CATEGORIAS}
    detalhe = []
    for r in linhas:
        if r["fora"]:
            continue
        if r["decisao_csv"] == "publicar":
            c = "publicado e certo" if r["acerto"] else "publicado e errado"
        elif r["rank_ramo"] == 1:
            c = "revisado, top-1 no ramo certo"
        elif r["rank_ramo"] <= 10:
            c = "revisado, ramo certo no top-2 a 10"
        else:
            c = "revisado, ramo ausente do top-10"
        cats[c] += 1
        detalhe.append((r["id"], r["disciplina"], r["rank_ramo"], r["decisao_csv"], c))
    assert sum(cats.values()) == len(validos) == 92, "categorias nao somam 92"

    # --- denominadores rotulados ------------------------------------------
    def resumo(dec, universo):
        n = sum(1 for r in linhas if r["id"] in universo and dec[r["id"]] == "publicar")
        a = sum(1 for r in linhas if r["id"] in universo and dec[r["id"]] == "publicar" and r["acerto"])
        return {"publicadas": n, "acertos": a, "precisao": round(a / n, 4) if n else None,
                "cobertura": round(n / len(universo), 4) if universo else None}

    fora_ids = [q for q in pub.index if q not in set(ids)]
    pub_fora = int((pub.loc[fora_ids, "decisao"] == "publicar").sum())
    den = {
        "in_sample_p_oof_100": resumo(dec_oof, set(ids)),
        "entregue_csv_p_all_100": resumo(dec_csv, set(ids)),
        "entregue_csv_p_all_659": {
            "publicadas": int((pub["decisao"] == "publicar").sum()),
            "revisar": int((pub["decisao"] == "revisar").sum()),
            "fora": int((pub["decisao"] == "fora").sum()) if "fora" in set(pub["decisao"]) else 0,
        },
        # Nas 559 nao ha rotulo: so a contagem e observavel (precisao fica None).
        "fora_da_folha_559": {
            "publicadas": pub_fora,
            "n": len(fora_ids),
            "cobertura": round(pub_fora / len(fora_ids), 4),
            "precisao": None,
        },
    }
    assert pub_fora + den["entregue_csv_p_all_100"]["publicadas"] == den["entregue_csv_p_all_659"]["publicadas"]

    # --- por disciplina ----------------------------------------------------
    disc = {}
    for r in linhas:
        if r["fora"]:
            continue
        d = disc.setdefault(r["disciplina"], {"n": 0, "publicadas": 0, "acertos": 0,
                                              "revisadas_com_top1_certo": 0})
        d["n"] += 1
        if r["decisao_csv"] == "publicar":
            d["publicadas"] += 1
            d["acertos"] += int(r["acerto"])
        elif r["rank_ramo"] == 1:
            d["revisadas_com_top1_certo"] += 1

    # --- Q0202 e o unico erro publicado na folha --------------------------
    erros = [r for r in linhas if not r["fora"] and r["decisao_csv"] == "publicar" and not r["acerto"]]
    q = erros[0] if erros else None
    q0202 = None
    if q:
        q0202 = {k: q[k] for k in ("id", "disciplina", "ramo_previsto", "ramo_aceitos",
                                   "rank_ramo", "p_oof", "consenso")}

    # --- diagnostico da cobertura deixada na mesa -------------------------
    top1_revisado = [r for r in linhas if not r["fora"] and r["decisao_csv"] == "revisar"
                     and r["rank_ramo"] == 1]
    fora10 = [r for r in linhas if not r["fora"] and r["rank_ramo"] > 10]

    saida = {
        "regra": {"tau": tau, "consenso_min": cons_min},
        "n_folha": len(ids), "n_validas": len(validos), "n_fora": len(fora),
        "denominadores": den,
        "crosstab_rank_x_decisao": {
            "linhas": [{"faixa": i, **{c: int(tab.loc[i, c]) for c in tab.columns},
                        "total": int(tab.loc[i].sum())} for i in tab.index],
            "colunas": {c: int(tab[c].sum()) for c in tab.columns},
            "total": int(tab.values.sum()),
        },
        "categorias": {c: cats[c] for c in CATEGORIAS},
        "por_disciplina": disc,
        "erro_publicado": q0202,
        "cobertura_na_mesa": {
            "revisadas_com_top1_certo": len(top1_revisado),
            "ramo_ausente_do_top10": len(fora10),
            "ids_fora_do_top10": [r["id"] for r in fora10],
        },
        "checks": {
            "ids_unicos": True,
            "crosstab_soma_92": int(tab.values.sum()) == 92,
            "categorias_soma_92": sum(cats.values()) == 92,
        },
    }
    (ARTEFATOS / "diagnostico.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- resumo no terminal ------------------------------------------------
    print("=== 1. recuperacao x decisao (92 validas, regra do entregavel) ===")
    print(tab.assign(total=tab.sum(axis=1)).to_string())
    print("colunas:", saida["crosstab_rank_x_decisao"]["colunas"], "total:", tab.values.sum())
    print("\n=== 2. categorias exclusivas (somam 92) ===")
    for c in CATEGORIAS:
        print(f"  {c:38s} {cats[c]:3d}")
    print("\n=== 3. denominadores ===")
    for nome, d in den.items():
        print(f"  {nome:26s} {d}")
    print("\n=== 4. por disciplina ===")
    for d, v in sorted(disc.items(), key=lambda x: -x[1]["n"]):
        print(f"  {d:38s} n={v['n']:2d} pub={v['publicadas']:2d} "
              f"acertos={v['acertos']:2d} revisadas_top1_certo={v['revisadas_com_top1_certo']:2d}")
    if q0202:
        print("\n=== 5. erro publicado na folha ===")
        print(" ", q0202)
    print("\n=== 6. cobertura na mesa ===")
    print(f"  revisadas com top-1 no ramo certo: {len(top1_revisado)}")
    print(f"  ramo ausente do top-10: {len(fora10)} -> {[r['id'] for r in fora10]}")
    print("\nartefato:", ARTEFATOS / "diagnostico.json")


if __name__ == "__main__":
    main()
