"""Analise do A/B de recuperacao (dicionario no retrieval). Offline, sem API.

Le os votos ja produzidos por `src.experimentos.ab_juiz --rodar` e consolida a comparacao NO
NIVEL DA DECISAO, com e sem o verificador, e por disciplina de Legislacao Especial.

  .venv/bin/python -m src.experimentos.ab_dic --rotulos data/rotulos_opus.tsv \
      --configs atual tfidf+filho tfidf+filho+dic --par tfidf+filho tfidf+filho+dic
  .venv/bin/python -m src.experimentos.ab_dic --rotulos outputs/amostra_rotulagem.csv --configs atual

Le `outputs/experimentos/ab_juiz/<config><tag>.votos.jsonl` (tag vazio para a rotulagem
padrao). `atual` usa o candidatos.json da entrega (so a ancora). Escreve
`outputs/experimentos/ab_juiz/analise<tag>.json` e imprime a tabela.
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

import pandas as pd

from src.config import OUT
from src.decide import agregar, decidir
from src.eval import carregar_rotulos
from src.temas import Arvore

EXP = OUT / "experimentos" / "ab_juiz"
MAPA = {"Direito Penal": "Penal", "Direito Processual Penal": "Processo Penal"}
LEG = "Direito Penal - Legislação Especial"


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def _decisao(arv, origem, votos, ver_i, i):
    v = votos + ([ver_i] if ver_i else [])
    ag = agregar(arv, v, votos[0]["tema_id"] or "")
    dec, mot = decidir(arv, ag)
    if dec == "publicar" and ag["tema"] in arv.gemeos():
        if arv.raiz(ag["tema"]) != MAPA.get(origem.get(i, ""), origem.get(i, "")):
            dec = "revisar"
    return dec, (ag["tema"] if dec == "publicar" else None)


def _carrega(cfg, tag):
    p = EXP / f"{cfg}{tag}.votos.jsonl"
    if not p.exists():
        return None
    return {json.loads(l)["id"]: json.loads(l)["votes"] for l in p.open(encoding="utf-8")}


def analisa(arv, origem, ver, rotmap, votos, ids):
    out = {}
    for com_ver in (False, True):
        pub = corr = gem_ = 0
        leg = [0, 0]
        erros = []
        for i in ids:
            dec, tema = _decisao(arv, origem, votos[i], ver.get(i) if com_ver else None, i)
            if dec != "publicar":
                continue
            pub += 1
            ok = bool(tema) and arv.relacionado(tema, rotmap[i])
            corr += int(ok)
            gem_ += int(bool(tema) and arv.titulo.get(tema) == arv.titulo.get(rotmap[i])
                        and arv.raiz(tema) != arv.raiz(rotmap[i]))
            if arv.raiz(rotmap[i]) == LEG:
                leg[0] += 1
                leg[1] += int(ok)
            if not ok:
                erros.append(i)
        lo, hi = wilson(corr, pub)
        out["com_verificador" if com_ver else "sem_verificador"] = {
            "publicadas": pub,
            "concordancia": round(corr / pub, 4) if pub else None,
            "corretas": corr,
            "wilson95": [round(lo, 2), round(hi, 2)],
            "leg_esp": f"{leg[1]}/{leg[0]}",
            "gemeos": gem_,
            "erros_ids": erros,
        }
    return out


def par(arv, origem, ver, rotmap, V, a, b, ids):
    """Diferenca pareada a->b no nivel da decisao (com verificador)."""
    trocas, ganho, perda, neutro = [], 0, 0, 0
    for i in ids:
        da, ta = _decisao(arv, origem, V[a][i], ver.get(i), i)
        db, tb = _decisao(arv, origem, V[b][i], ver.get(i), i)
        if (da, ta) == (db, tb):
            continue
        oka = da == "publicar" and bool(ta) and arv.relacionado(ta, rotmap[i])
        okb = db == "publicar" and bool(tb) and arv.relacionado(tb, rotmap[i])
        if oka == okb:
            neutro += 1
        elif okb:
            ganho += 1
        else:
            perda += 1
        trocas.append({"id": i, "ref": rotmap[i], "de": f"{da}:{ta}", "para": f"{db}:{tb}",
                       "ok_de": oka, "ok_para": okb})
    return {"de": a, "para": b, "mudaram": len(trocas), "ganho": ganho, "perda": perda,
            "neutro": neutro, "trocas": trocas}


def main():
    ap = argparse.ArgumentParser(description="Analise do A/B de recuperacao (offline).")
    ap.add_argument("--rotulos", default="data/rotulos_opus.tsv")
    ap.add_argument("--configs", nargs="*", default=["atual", "tfidf+filho", "tfidf+filho+dic"])
    ap.add_argument("--par", nargs=2, default=None, metavar=("A", "B"))
    args = ap.parse_args()

    arv = Arvore()
    tag = "_" + Path(args.rotulos).stem if args.rotulos != str(OUT / "amostra_rotulagem.csv") else ""
    rdf, col = carregar_rotulos(args.rotulos)
    rotmap = dict(zip(rdf.id, rdf[col]))
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    origem = q["disciplina_origem"].to_dict()
    ver = {}
    vp = OUT / "votos_verificacao.jsonl"
    if vp.exists():
        ver = {json.loads(l)["id"]: json.loads(l)["vote"] for l in vp.open(encoding="utf-8")}

    V = {}
    for c in args.configs:
        v = _carrega(c, tag)
        if v is not None:
            V[c] = v

    res = {"rotulos": str(args.rotulos), "configs": {}}
    ids_comum = [i for i in rotmap if all(i in V[c] for c in V)]
    print(f"=== A/B x {Path(args.rotulos).name} | questoes comparaveis: {len(ids_comum)} ===")
    for c, v in V.items():
        ids = [i for i in rotmap if i in v]
        res["configs"][c] = {"n": len(ids), **analisa(arv, origem, ver, rotmap, v, ids)}
        a = res["configs"][c]
        for k in ("sem_verificador", "com_verificador"):
            m = a[k]
            print(f"  {c:16s} [{k:15s}] pub={m['publicadas']:3d} conc={m['concordancia']} "
                  f"({m['corretas']}/{m['publicadas']}) W95={m['wilson95']} legesp={m['leg_esp']} gemeos={m['gemeos']}")

    if args.par and all(c in V for c in args.par):
        r = par(arv, origem, ver, rotmap, V, args.par[0], args.par[1], ids_comum)
        res["par"] = r
        print(f"\n[diferenca pareada {r['de']} -> {r['para']}] mudaram={r['mudaram']} "
              f"ganho={r['ganho']} perda={r['perda']} neutro={r['neutro']}")
        for t in r["trocas"]:
            flag = "=" if t["ok_de"] == t["ok_para"] else ("+" if t["ok_para"] else "-")
            print(f"   {flag} {t['id']} ref={t['ref']} {t['de']} -> {t['para']}")

    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / f"analise{tag}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nescrito: {EXP}/analise{tag}.json")


if __name__ == "__main__":
    main()
