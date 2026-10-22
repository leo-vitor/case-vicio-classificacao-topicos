"""Teste aninhado de veto e promocao por evidencia legal.

Baseline: regra atual (consenso e probabilidade), com (tau, c) escolhidos dentro
do treino de cada dobra. As variantes aplicam a evidencia apenas no teste.

Protocolo: 5 repeticoes x 5 dobras externas. Cada repeticao e medida; para o
pareado por questao, uma questao e publicada se aparecer publicada em pelo menos
3 das 5 repeticoes (definicao registrada em docs/rodada2.md antes do teste).

Uso, da pasta fase2/:
    python -m src.experimentos.decisao_evidencia
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.artefato import base
from src.auditoria import nested_corrigido
from src.config import ALVO_PRECISAO, ARTEFATOS, N_REPEATS
from src.decisao import escolher_regra, modelo
from src.protocolo import acerto, wilson

OUT = ARTEFATOS / "experimentos"
FONTE = "LEI"

def p_interno_grupo(X, y, folds_grupo, k):
    """Igual a auditoria.p_interno, mas restrito a uma repeticao de 5 dobras."""
    tr, te = folds_grupo[k]
    teste = set(int(i) for i in te)
    tr_idx = np.array([i for i in range(len(y)) if i not in teste])
    pos = {int(g): j for j, g in enumerate(tr_idx)}
    p_tr = np.zeros(len(tr_idx))
    for j, (a, b) in enumerate(folds_grupo):
        if j == k:
            continue
        a_in = [pos[int(i)] for i in a if int(i) in pos]
        b_in = [pos[int(i)] for i in b if int(i) in pos]
        if not a_in or not b_in:
            continue
        clf = modelo().fit(X.iloc[tr_idx[a_in]], y[tr_idx[a_in]])
        p_tr[b_in] = clf.predict_proba(X.iloc[tr_idx[b_in]])[:, 1]
    return tr_idx, p_tr, te

def metricas(pub, y):
    m = int(np.sum(pub))
    ac = int(np.sum(y[pub]))
    lo, hi = wilson(ac, m)
    return {
        "publicados": m, "acertos": ac,
        "precisao": round(ac / m, 4) if m else None,
        "precisao_wilson": [round(float(lo), 4), round(float(hi), 4)] if m else [0.0, 1.0],
        "cobertura": round(m / len(y), 4),
    }

def main():
    b = base()
    arv, gold, ids, X, y, cons, pred = (
        b["arv"], b["gold"], b["ids"], b["X"], b["y"], b["cons"], b["pred"]
    )
    ev = pd.read_csv(OUT / "evidencia_legal.csv", dtype=str).fillna("").set_index("id")
    ramo_lei = []
    for qid in ids:
        d = json.loads(ev.loc[qid, "ramo_unico_por_fonte"])
        ramo_lei.append(d.get(FONTE))
    ramo_lei = np.array([r if r else None for r in ramo_lei], dtype=object)
    tem_unico = np.array([r is not None for r in ramo_lei])

    folds = b["folds"]
    assert len(folds) == 25
    grupos = [folds[i * 5:(i + 1) * 5] for i in range(N_REPEATS)]

    nomes = ["baseline", "veto", "promocao"]
    pubs = {n: np.zeros((N_REPEATS, len(y)), dtype=bool) for n in nomes}
    regras = []
    gatilhos = {"unico_lei": int(tem_unico.sum()), "veto_muda": 0, "promocao_muda": 0}
    detalhe_dobras = []

    for rep, grupo in enumerate(grupos):
        for k in range(5):
            tr_idx, p_tr, te = p_interno_grupo(X, y, grupo, k)
            lam, c = escolher_regra(p_tr, cons[tr_idx], y[tr_idx], ALVO_PRECISAO)
            regra = {"repeat": rep, "dobra": k,
                     "limiar": None if lam is None else round(float(lam), 4),
                     "consenso": c}
            regras.append(regra)
            if lam is None:
                continue
            clf = modelo().fit(X.iloc[tr_idx], y[tr_idx])
            te_idx = np.array([int(i) for i in te])
            p_te = clf.predict_proba(X.iloc[te_idx])[:, 1]
            base_mask = (cons[te_idx] >= c) & (p_te >= lam)

            unico_te = tem_unico[te_idx]
            ev_te = ramo_lei[te_idx]
            pred_te = np.array([pred[i] for i in te_idx], dtype=object)
            difere = unico_te & np.array([e != p for e, p in zip(ev_te, pred_te)])
            coincide = unico_te & np.array([e == p for e, p in zip(ev_te, pred_te)])
            alto_consenso = cons[te_idx] >= 0.75

            veto = base_mask & ~difere
            promo = base_mask | (coincide & alto_consenso)

            pubs["baseline"][rep, te_idx] |= base_mask
            pubs["veto"][rep, te_idx] |= veto
            pubs["promocao"][rep, te_idx] |= promo
            gatilhos["veto_muda"] += int(np.sum(base_mask & difere))
            gatilhos["promocao_muda"] += int(np.sum(promo & ~base_mask))
            detalhe_dobras.append({
                **regra,
                "n_teste": len(te_idx),
                "baseline_publica": int(base_mask.sum()),
                "veto_remove": int((base_mask & difere).sum()),
                "promocao_adiciona": int((promo & ~base_mask).sum()),
            })

    major = {n: pubs[n].sum(axis=0) >= 3 for n in nomes}
    corretas = np.array([acerto(arv, gold.loc[qid, "alvos"], p) for qid, p in zip(ids, pred)])

    resultado = {
        "fonte": FONTE,
        "n": len(y),
        "gatilhos": gatilhos,
        "regras": regras,
        "por_repeticao": {},
        "majoritaria": {},
        "criterio": {},
        "detalhe_dobras": detalhe_dobras,
    }

    for n in nomes:
        por_rep = []
        for rep in range(N_REPEATS):
            met = metricas(pubs[n][rep], y)
            por_rep.append(met)
        resultado["por_repeticao"][n] = {
            "precisao_media": round(float(np.mean([m["precisao"] for m in por_rep])), 4),
            "precisao_min": min(m["precisao"] for m in por_rep),
            "precisao_max": max(m["precisao"] for m in por_rep),
            "cobertura_media": round(float(np.mean([m["cobertura"] for m in por_rep])), 4),
            "cobertura_min": min(m["cobertura"] for m in por_rep),
            "cobertura_max": max(m["cobertura"] for m in por_rep),
            "publicados_media": round(float(np.mean([m["publicados"] for m in por_rep])), 2),
        }
        resultado["majoritaria"][n] = metricas(major[n], y)
        resultado["majoritaria"][n]["ids"] = [qid for qid, p in zip(ids, major[n]) if p]

    base_corr = major["baseline"] & corretas
    for n in ["veto", "promocao"]:
        var_corr = major[n] & corretas
        ganhos = int(np.sum(var_corr & ~base_corr))
        perdas = int(np.sum(base_corr & ~var_corr))
        base_m = resultado["majoritaria"]["baseline"]
        var_m = resultado["majoritaria"][n]
        passa = bool(
            var_m["precisao"] is not None and base_m["precisao"] is not None
            and var_m["precisao"] >= base_m["precisao"]
            and var_m["cobertura"] > base_m["cobertura"]
            and ganhos > perdas
        )
        resultado["criterio"][n] = {
            "ganhos": ganhos, "perdas": perdas,
            "precisao_nao_cai": bool(var_m["precisao"] >= base_m["precisao"]),
            "cobertura_sobe": bool(var_m["cobertura"] > base_m["cobertura"]),
            "mais_ganhos_que_perdas": bool(ganhos > perdas),
            "passa": passa,
        }

    corr_rep = {n: np.array([[bool(pubs[n][r, i] and corretas[i]) for i in range(len(y))]
                             for r in range(N_REPEATS)]) for n in nomes}
    resultado["pareado_por_repeticao"] = {}
    resultado["criterio_por_repeticao"] = {}
    for n in ["veto", "promocao"]:
        cb = corr_rep["baseline"].sum(axis=0)
        cv = corr_rep[n].sum(axis=0)
        ganhos = int(np.sum(cv > cb))
        perdas = int(np.sum(cv < cb))
        base_p = resultado["por_repeticao"]["baseline"]["precisao_media"]
        var_p = resultado["por_repeticao"][n]["precisao_media"]
        base_c = resultado["por_repeticao"]["baseline"]["cobertura_media"]
        var_c = resultado["por_repeticao"][n]["cobertura_media"]
        resultado["pareado_por_repeticao"][n] = {
            "ganhos": ganhos, "perdas": perdas, "empates": int(len(y) - ganhos - perdas)
        }
        resultado["criterio_por_repeticao"][n] = {
            "ganhos": ganhos, "perdas": perdas,
            "precisao_nao_cai": bool(var_p >= base_p),
            "cobertura_sobe": bool(var_c > base_c),
            "mais_ganhos_que_perdas": bool(ganhos > perdas),
            "passa": bool(var_p >= base_p and var_c > base_c and ganhos > perdas),
        }

    sanidade = nested_corrigido(X, y, cons, folds)
    resultado["sanidade_baseline_5_dobras_existente"] = {
        k: v for k, v in sanidade.items() if k not in ("pub", "regras")
    }

    (OUT / "decisao_evidencia.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    linhas = ["# Evidencia legal na decisao", ""]
    linhas.append("Fonte usada: lei especial (unica que passou na Etapa 3).")
    linhas.append(f"- questoes com ramo unico de lei: {gatilhos['unico_lei']}/100")
    linhas.append(f"- veto mudou {gatilhos['veto_muda']} publicacoes (dobra x questao)")
    linhas.append(f"- promocao adicionou {gatilhos['promocao_muda']} publicacoes (dobra x questao)")
    linhas += ["", "| variante | publicadas | acertos | precisao | IC Wilson | cobertura | ganhos | perdas | passa |"]
    linhas.append("|---|---:|---:|---:|---|---:|---:|---:|---|")
    for n in nomes:
        m = resultado["majoritaria"][n]
        crit = resultado["criterio"].get(n, {})
        linhas.append(
            f"| {n} | {m['publicados']} | {m['acertos']} | "
            f"{m['precisao']:.3f} | {m['precisao_wilson'][0]:.2f}-{m['precisao_wilson'][1]:.2f} | "
            f"{m['cobertura']:.3f} | {crit.get('ganhos', '-')} | {crit.get('perdas', '-')} | "
            f"{'sim' if crit.get('passa') else 'nao'} |"
        )
    linhas += ["", "Sensibilidade por repeticao (media):"]
    linhas.append("| variante | precisao media | cobertura media | ganhos | perdas | passa |")
    linhas.append("|---|---:|---:|---:|---:|---|")
    for n in nomes:
        rp = resultado["por_repeticao"][n]
        cp = resultado["criterio_por_repeticao"].get(n, {})
        linhas.append(
            f"| {n} | {rp['precisao_media']:.3f} | {rp['cobertura_media']:.3f} | "
            f"{cp.get('ganhos', '-')} | {cp.get('perdas', '-')} | "
            f"{'sim' if cp.get('passa') else 'nao'} |"
        )
    linhas += ["", "Sanidade do baseline existente (5 dobras): "
               f"{resultado['sanidade_baseline_5_dobras_existente']['acertos']}/"
               f"{resultado['sanidade_baseline_5_dobras_existente']['publicados']}."]
    (OUT / "decisao_evidencia.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print(json.dumps({k: resultado[k] for k in
                      ["n", "gatilhos", "por_repeticao", "majoritaria", "criterio",
                       "sanidade_baseline_5_dobras_existente"]},
                     ensure_ascii=False, indent=2))
    print(f"Saidas: {OUT / 'decisao_evidencia.json'} e .md")

if __name__ == "__main__":
    main()
