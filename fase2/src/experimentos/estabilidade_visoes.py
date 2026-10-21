"""Estabilidade da busca entre enunciado, alternativas e comando.

Descritivo. Nao muda a decisao. Mede se a concordancia das tres visoes separa
acertos de erros do modelo de texto completo.

Uso, da pasta fase2/:
    python -m src.experimentos.estabilidade_visoes
"""
from __future__ import annotations

import json

import numpy as np

from src.artefato import base
from src.clean import load_questoes, strip_html
from src.config import ARTEFATOS
from src.decisao import promover
from src.enriquecimento import carregar as carregar_artefato, textos as textos_enriquecidos
from src.protocolo import acerto, wilson
from src.recuperacao import Busca, ordem_desc


OUT = ARTEFATOS / "experimentos"


def visoes_questao(q):
    alts = q.get("alternativas") or {}
    alternativas = "\n".join(f"{k}) {strip_html(str(v))}" for k, v in alts.items())
    return {
        "enunciado": strip_html(q.get("enunciado_html") or ""),
        "alternativas": alternativas,
        "comando": strip_html(q.get("comando") or ""),
    }


def main():
    b = base()
    arv, gold, ids, pred = b["arv"], b["gold"], b["ids"], b["pred"]
    pool = b["pool"]
    busca = Busca(textos_enriquecidos(arv, pool, carregar_artefato()))
    raw = {q["id"]: q for q in load_questoes()}
    visoes = {qid: visoes_questao(raw[qid]) for qid in ids}

    ramos = {v: [] for v in ("enunciado", "alternativas", "comando")}
    for v in ramos:
        textos = [visoes[qid][v] for qid in ids]
        M = busca.scores("rrf_all", textos)
        for i in range(len(ids)):
            t = pool[int(ordem_desc(M[i])[0])]
            ramos[v].append(promover(arv, t))

    linhas = []
    for i, qid in enumerate(ids):
        trio = (ramos["enunciado"][i], ramos["alternativas"][i], ramos["comando"][i])
        concorda = len(set(trio)) == 1
        linhas.append({
            "id": qid,
            "enunciado": trio[0], "alternativas": trio[1], "comando": trio[2],
            "concorda": bool(concorda),
            "pred": pred[i],
            "correto": bool(acerto(arv, gold.loc[qid, "alvos"], pred[i])),
        })

    def bloco(sel, rotulo):
        n = len(sel)
        ac = sum(1 for x in sel if x["correto"])
        lo, hi = wilson(ac, n)
        return {"grupo": rotulo, "n": n, "acertos": ac,
                "precisao": round(ac / n, 4) if n else None,
                "wilson": [round(float(lo), 4), round(float(hi), 4)]}

    conc = [x for x in linhas if x["concorda"]]
    disc = [x for x in linhas if not x["concorda"]]
    r_conc = bloco(conc, "tres visoes concordantes")
    r_disc = bloco(disc, "pelo menos uma discordancia")
    diff = ((r_conc["precisao"] or 0) - (r_disc["precisao"] or 0)) * 100
    claro = bool(r_conc["n"] >= 10 and r_disc["n"] >= 10 and abs(diff) >= 15)

    saida = {
        "n": len(linhas),
        "concordantes": r_conc, "discordantes": r_disc,
        "diferenca_pp": round(float(diff), 2),
        "separacao_clara": claro,
        "detalhe": linhas,
    }
    (OUT / "estabilidade_visoes.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md = ["# Estabilidade entre visoes", "",
          f"- concordantes: {r_conc['acertos']}/{r_conc['n']} "
          f"({r_conc['precisao']:.2f}; IC {r_conc['wilson'][0]:.2f}-{r_conc['wilson'][1]:.2f})",
          f"- discordantes: {r_disc['acertos']}/{r_disc['n']} "
          f"({r_disc['precisao']:.2f}; IC {r_disc['wilson'][0]:.2f}-{r_disc['wilson'][1]:.2f})",
          f"- diferenca: {diff:+.1f} pontos percentuais",
          f"- separacao clara (>=15 p.p. e n>=10 em cada grupo): {'sim' if claro else 'nao'}"]
    (OUT / "estabilidade_visoes.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({k: saida[k] for k in
                      ["n", "concordantes", "discordantes", "diferenca_pp", "separacao_clara"]},
                     ensure_ascii=False, indent=2))
    print(f"Saidas: {OUT / 'estabilidade_visoes.json'} e .md")


if __name__ == "__main__":
    main()
