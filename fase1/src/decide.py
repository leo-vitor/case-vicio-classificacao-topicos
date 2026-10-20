"""Etapa 4: regras que transformam os votos em publicar / revisar / fora.

Ideias centrais:
- Se os votos divergem entre subtemas do MESMO tema, publica no tema pai (a regua aceita pai e filho).
- Se divergem entre temas diferentes, vai para revisao com a sugestao mais votada.
- Temas 'lixeira' (muitas questoes na origem) exigem confianca extra.
"""
import csv
import json
from collections import Counter
from math import ceil

import pandas as pd

from src.config import LIXEIRA_EXTRA, LIXEIRA_MIN_Q, OUT, THRESH
from src.temas import Arvore


def no_comum(arv, ids):
    """Menor no (mais profundo) relacionado a todos os votos. None se nao houver."""
    cand = set(ids) | {arv.parent.get(i) for i in ids if arv.parent.get(i)}
    ok = [c for c in cand if arv.publicavel(c) and all(arv.relacionado(c, i) for i in ids)]
    if not ok:
        return None
    return max(ok, key=lambda c: arv.nivel[c])


def agregar(arv, votes, fallback_top):
    n = len(votes)
    foras = [v for v in votes if v["fora"]]
    if len(foras) * 2 > n:
        motivo = Counter(v["motivo"] for v in foras).most_common(1)[0][0] or "nenhum tema serve"
        return {"kind": "fora", "tema": None, "score": len(foras) / n, "motivo": motivo, "extras": []}
    validos = [v for v in votes if not v["fora"] and v["tema_id"]]
    if not validos:
        return {"kind": "sem_voto", "tema": fallback_top, "score": 0.0, "motivo": votes[0]["motivo"], "extras": []}
    ids = [v["tema_id"] for v in validos]
    top, cnt = Counter(ids).most_common(1)[0]
    conf_media = sum(v["conf"] for v in validos) / len(validos)
    if len(set(ids)) == 1:
        kind, node, frac = "unanime", top, len(validos) / n
    else:
        node = no_comum(arv, ids)
        if node is not None:
            kind, frac = "mesmo_ramo", len(validos) / n
        else:
            kind, node, frac = "divergente", top, cnt / n
    ex = Counter(e for v in validos for e in v["extras"])
    extras = [e for e, c in ex.most_common() if c >= ceil(n / 2) and e != node and arv.publicavel(e)][:3]
    if arv.nivel.get(node) == 2:
        pai = arv.parent.get(node)
        if any(arv.parent.get(e) == pai for e in extras):
            node = pai
            extras = [e for e in extras if e != pai]    
    return {"kind": kind, "tema": node, "score": conf_media * frac, "motivo": "", "extras": extras, "ids": ids}


def decidir(arv, ag, thresh=THRESH):
    if ag["kind"] == "fora":
        return "fora", ""
    if ag["kind"] in ("unanime", "mesmo_ramo"):
        t = thresh + (LIXEIRA_EXTRA if arv.nq.get(ag["tema"], 0) >= LIXEIRA_MIN_Q else 0)
        if ag["score"] >= t:
            return "publicar", ""
        return "revisar", f"confianca {ag['score']:.2f} abaixo do limiar {t:.2f}"
    if ag["kind"] == "divergente":
        return "revisar", "rodadas divergem entre temas: " + ";".join(sorted(set(ag["ids"])))
    return "revisar", ag["motivo"]


def main():
    arv = Arvore()
    cands = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    linhas, agreg = [], []
    gem = arv.gemeos()
    orig = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")["disciplina_origem"]
    MAPA = {"Direito Penal": "Penal", "Direito Processual Penal": "Processo Penal"}
    ver = {}
    vp = OUT / "votos_verificacao.jsonl"
    if vp.exists():
        with open(vp, encoding="utf-8") as fv:
            for lv in fv:
                x = json.loads(lv)
                ver[x["id"]] = x["vote"]
    with open(OUT / "votos.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] in ver:
                r["votes"] = r["votes"] + [ver[r["id"]]]
            fb = cands[r["id"]]["candidatos"][0]
            ag = agregar(arv, r["votes"], fb)
            dec, motivo = decidir(arv, ag)
            if dec == "publicar" and ag["tema"] in gem:
                o = orig[r["id"]]
                if arv.raiz(ag["tema"]) != MAPA.get(o, o):
                    dec, motivo = "revisar", "tema duplicado entre disciplinas: confirmar qual gemeo usar"            
            motivo = motivo or ag.get("motivo", "")
            tema = "" if dec == "fora" else ag["tema"]
            linhas.append(
                {
                    "id": r["id"],
                    "decisao": dec,
                    "tema_central_id": tema,
                    "extras_ids": ";".join(ag["extras"]) if dec != "fora" else "",
                    "confianca": 0.0 if dec == "fora" else round(min(0.99, ag["score"]), 2),
                    "motivo": motivo if dec != "publicar" else "",
                }
            )
            agreg.append({"id": r["id"], "kind": ag["kind"], "tema": ag["tema"] or "", "score": round(ag["score"], 4), "nq": arv.nq.get(ag["tema"], 0)})
    pd.DataFrame(agreg).to_csv(OUT / "agregado.csv", index=False)
    cols = ["id", "decisao", "tema_central_id", "extras_ids", "confianca", "motivo"]
    pd.DataFrame(linhas)[cols].to_csv(OUT.parent / "publicacao.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    cont = Counter(l["decisao"] for l in linhas)
    print("Decisoes:", dict(cont), f"| cobertura = {cont['publicar'] / len(linhas):.1%}")


if __name__ == "__main__":
    main()
