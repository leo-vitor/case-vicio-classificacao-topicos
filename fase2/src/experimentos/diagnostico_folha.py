"""Diagnostico descritivo da evidencia legal na folha-verdade.

Nao decide nada. Para cada fonte (CP Parte Geral, CP Parte Especial, CPP, lei
especial) restringe as questoes da folha que tem UM unico ramo indicado por
aquela fonte e compara evidencia e modelo pela regua do case.

Uso, da pasta fase2/:
    python -m src.experimentos.diagnostico_folha
"""
from __future__ import annotations

import json
from collections import OrderedDict

import pandas as pd

from src.artefato import base
from src.config import ARTEFATOS, DATA
from src.protocolo import acerto, wilson


OUT = ARTEFATOS / "experimentos"
FONTES = ["CP_PG", "CP_PE", "CPP", "LEI"]


def avaliar_fonte(df, fonte, arv):
    g = df[df["fonte"] == fonte].copy()
    n = len(g)
    e = int(g["ev"].sum())
    m = int(g["model"].sum())
    both = int((g["ev"] & g["model"]).sum())
    ev_only = int((g["ev"] & ~g["model"]).sum())
    model_only = int((~g["ev"] & g["model"]).sum())
    none = int((~g["ev"] & ~g["model"]).sum())
    lo_e, hi_e = wilson(e, n)
    lo_m, hi_m = wilson(m, n)
    passa = bool(n >= 5 and e / n >= m / n and ev_only > model_only)
    return {
        "fonte": fonte, "n": n, "ev_acertos": e, "ev_precisao": e / n if n else None,
        "ev_wilson": [round(lo_e, 4), round(hi_e, 4)],
        "modelo_acertos": m, "modelo_precisao": m / n if n else None,
        "modelo_wilson": [round(lo_m, 4), round(hi_m, 4)],
        "ambos": both, "so_evidencia": ev_only, "so_modelo": model_only, "nenhum": none,
        "ganhos": ev_only, "perdas": model_only, "passa": passa,
        "ids": g["id"].tolist(),
    }


def main():
    b = base()
    arv, gold, ids, pred = b["arv"], b["gold"], b["ids"], b["pred"]
    ev = pd.read_csv(OUT / "evidencia_legal.csv", dtype=str).fillna("").set_index("id")

    linhas = []
    for i, qid in enumerate(ids):
        d = json.loads(ev.loc[qid, "ramo_unico_por_fonte"])
        for fonte in FONTES:
            ramo = d.get(fonte)
            if not ramo:
                continue
            alvos = gold.loc[qid, "alvos"]
            linhas.append({
                "id": qid, "fonte": fonte, "ramo": ramo, "pred": pred[i],
                "gold": gold.loc[qid, "tema_central_id"],
                "extras": gold.loc[qid, "extras_ids"],
                "fora": gold.loc[qid, "fora"],
                "ev": bool(acerto(arv, alvos, ramo)),
                "model": bool(acerto(arv, alvos, pred[i])),
            })

    # Uniao dos artigos (CP + CPP): a leitura exploratoria de "artigos 4 de 7"
    # era a uniao, nao cada fonte separada. Mantemos as duas visoes.
    por_q = {}
    for row in linhas:
        if row["fonte"] in ("CP_PG", "CP_PE", "CPP"):
            por_q.setdefault(row["id"], []).append(row)
    for qid, rs in por_q.items():
        ramos = {r["ramo"] for r in rs}
        if len(ramos) == 1:
            r = rs[0]
            linhas.append({**r, "fonte": "ARTIGOS", "ramo": next(iter(ramos))})

    df = pd.DataFrame(linhas)
    resultados = OrderedDict()
    for fonte in FONTES + ["ARTIGOS"]:
        resultados[fonte] = avaliar_fonte(df, fonte, arv)

    # Cruzamento do conjunto que interessa para a decisao: so as fontes que
    # passaram no criterio escrito.
    passam = [f for f in FONTES if resultados[f]["passa"]]
    resultado = {
        "n_folha": len(ids),
        "fontes": resultados,
        "fontes_que_passam": passam,
        "detalhe": df.to_dict(orient="records"),
        "nota_exploratoria": (
            "O teste exploratorio do PROVENIENCIA dizia lei especial 8/9. "
            "O extrator reproduz 7/9: Q0090 cita a Lei 9.099 em uma alternativa "
            "distratora e o ramo da lei nao e o gold (5530)."
        ),
    }
    (OUT / "diagnostico_folha.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    linhas_md = ["# Diagnostico da evidencia legal na folha", ""]
    linhas_md.append("| fonte | n | evidencia | IC Wilson | modelo | IC Wilson | ambos | so ev | so modelo | passa |")
    linhas_md.append("|---|---:|---:|---|---:|---|---:|---:|---:|---|")
    for f, r in resultados.items():
        linhas_md.append(
            f"| {f} | {r['n']} | {r['ev_acertos']}/{r['n']} ({r['ev_precisao']:.2f}) | "
            f"{r['ev_wilson'][0]:.2f}-{r['ev_wilson'][1]:.2f} | "
            f"{r['modelo_acertos']}/{r['n']} ({r['modelo_precisao']:.2f}) | "
            f"{r['modelo_wilson'][0]:.2f}-{r['modelo_wilson'][1]:.2f} | "
            f"{r['ambos']} | {r['so_evidencia']} | {r['so_modelo']} | {'sim' if r['passa'] else 'nao'} |"
        )
    linhas_md += ["", "Fontes que passam para a Etapa 4: " + (", ".join(passam) or "nenhuma")]
    linhas_md += ["", "Hipotese: CP PG, CPP e lei especial indicam o assunto; CP PE erra mais."]
    linhas_md.append(
        "Leitura: CP PG empata com o modelo (5/6 vs 5/6) e tem 1 ganho e 1 perda; "
        "CP PE fica abaixo (3/6 vs 4/6); CPP tem n=1 e nao forma peso; "
        "lei especial supera (7/9 vs 4/9). A hipotese nao se confirma como um todo."
    )
    (OUT / "diagnostico_folha.md").write_text("\n".join(linhas_md) + "\n", encoding="utf-8")

    print(json.dumps({f: {k: v for k, v in r.items() if k != "ids"}
                      for f, r in resultados.items()}, ensure_ascii=False, indent=2))
    print(f"Saidas: {OUT / 'diagnostico_folha.json'} e .md")


if __name__ == "__main__":
    main()
