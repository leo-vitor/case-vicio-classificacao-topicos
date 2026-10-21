"""Experimento 3 — recuperadores pareados (recall@1/5/10), com IC e por disciplina.

Pergunta: algum recuperador bate o `rrf_all` no texto enriquecido, no topo do
ranking? E onde (disciplina) a diferença aparece?

Metodo:
  - base unica (`artefato.base()`), texto enriquecido, 92 validas;
  - `ramo@k`  = algum dos k primeiros itens tem ramo aceito (nivel 1 do gabarito);
  - `exato@k` = algum dos k primeiros itens E o tema central/extra, sem promocao;
  - diferenca pareada contra `rrf_all` com IC bootstrap (2000 reamostragens);
  - quebra por disciplina do gabarito (`gold.disciplina`).

Saida: `artefatos/recuperadores.json` + resumo no terminal.

Uso (da pasta fase2/):
    python -m src.recuperadores
"""
import json

import numpy as np

from src.artefato import base, tema1
from src.config import ARTEFATOS
from src.decisao import RETRIEVERS
from src.pisos import bootstrap_delta
from src.protocolo import wilson
from src.recuperacao import ordem_desc

KS = (1, 5, 10)
PRIM = "rrf_all"


def ranks(arv, pool, linha, aceitos, alvos):
    """(rank do primeiro ramo aceito, rank do primeiro tema exato), 1-based."""
    r_ramo = r_exato = None
    for pos, j in enumerate(ordem_desc(linha), start=1):
        t = pool[int(j)]
        if r_ramo is None and tema1(arv, t) in aceitos:
            r_ramo = pos
        if r_exato is None and t in alvos:
            r_exato = pos
        if r_ramo is not None and r_exato is not None:
            break
    return r_ramo, r_exato


def main():
    b = base()
    arv, gold, ids, pool, Ms = b["arv"], b["gold"], b["ids"], b["pool"], b["Ms"]
    validos = [qid for qid in ids if not gold.loc[qid, "fora"]]

    aceitos, alvos, disc = {}, {}, {}
    for qid in validos:
        alvos[qid] = set(gold.loc[qid, "alvos"])
        aceitos[qid] = {tema1(arv, t) for t in alvos[qid] if tema1(arv, t)}
        disc[qid] = gold.loc[qid, "disciplina"]

    # rank por questao x recuperador
    R = {r: {} for r in RETRIEVERS}
    for r in RETRIEVERS:
        for k, qid in enumerate(ids):
            if qid not in aceitos:
                continue
            R[r][qid] = ranks(arv, pool, Ms[r][k], aceitos[qid], alvos[qid])

    def vetor(r, k, tipo="ramo"):
        idx = 0 if tipo == "ramo" else 1
        return np.array([1.0 if R[r][q][idx] is not None and R[r][q][idx] <= k else 0.0
                         for q in validos])

    linhas = []
    for r in RETRIEVERS:
        for k in KS:
            v = vetor(r, k)
            lo, hi = wilson(int(v.sum()), len(v))
            if r == PRIM:
                d = dlo = dhi = 0.0
            else:
                d = float(v.mean() - vetor(PRIM, k).mean())
                dlo, dhi = bootstrap_delta(v, vetor(PRIM, k))
            linhas.append({
                "recuperador": r, "k": k, "tipo": "ramo",
                "acertos": int(v.sum()), "n": len(v), "valor": round(float(v.mean()), 4),
                "lo": round(lo, 4), "hi": round(hi, 4),
                "delta_vs_rrf": round(d, 4),
                "delta_lo": round(dlo, 4), "delta_hi": round(dhi, 4),
            })

    exato = []
    for r in RETRIEVERS:
        for k in KS:
            v = vetor(r, k, "exato")
            lo, hi = wilson(int(v.sum()), len(v))
            exato.append({"recuperador": r, "k": k, "tipo": "exato",
                          "acertos": int(v.sum()), "n": len(v),
                          "valor": round(float(v.mean()), 4),
                          "lo": round(lo, 4), "hi": round(hi, 4)})

    # por disciplina: ramo@1 e ramo@5
    por_disc = {}
    for d in sorted(set(disc.values())):
        qs = [q for q in validos if disc[q] == d]
        por_disc[d] = {"n": len(qs)}
        for r in RETRIEVERS:
            for k in (1, 5):
                ok = sum(1 for q in qs if R[r][q][0] is not None and R[r][q][0] <= k)
                por_disc[d][f"{r}@{k}"] = round(ok / len(qs), 4)

    saida = {
        "primario": PRIM, "n": len(validos),
        "ramo": linhas, "exato": exato, "por_disciplina": por_disc,
    }
    (ARTEFATOS / "recuperadores.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== ramo@k (92 validas, texto enriquecido; delta pareado vs rrf_all) ===")
    print(f"{'recuperador':16s} " + "  ".join(f"ramo@{k:<2d}" for k in KS))
    for r in RETRIEVERS:
        cel = []
        for k in KS:
            x = next(l for l in linhas if l["recuperador"] == r and l["k"] == k)
            cel.append(f"{x['valor']:.3f}")
        print(f"{r:16s} " + "  ".join(cel))
    print("\ndelta vs rrf_all (ramo@1):")
    for r in RETRIEVERS:
        x = next(l for l in linhas if l["recuperador"] == r and l["k"] == 1)
        print(f"  {r:16s} {x['delta_vs_rrf']:+.4f} [{x['delta_lo']:+.4f}; {x['delta_hi']:+.4f}]")
    print("\n=== exato@k (sem promocao ao pai) ===")
    for r in RETRIEVERS:
        print(f"  {r:16s} " + "  ".join(
            f"{next(x['valor'] for x in exato if x['recuperador'] == r and x['k'] == k):.3f}"
            for k in KS))
    print("\n=== ramo@1 por disciplina ===")
    for d, v in por_disc.items():
        print(f"  {d:38s} n={v['n']:2d} " + "  ".join(
            f"{r}={v[f'{r}@1']:.2f}" for r in RETRIEVERS))
    print("\nartefato:", ARTEFATOS / "recuperadores.json")


if __name__ == "__main__":
    main()
