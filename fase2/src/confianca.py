"""Etapa 3/4 — Confianca no nivel da QUESTAO + regra do pai.

Duas ideias que saem do protocolo:

1. REGRA DO PAI. Se o top-1 e um subtema (nivel 2), publicar o TEMA pai (nivel 1)
   nunca piora: a regua aceita o pai, e o pai cobre tambem os irmaos. Medido no
   gold, a promocao ganha 3-4 acertos e nunca perde.

2. CONFIANCA NO NIVEL DA QUESTAO. O que se quer estimar e P(o no publicado estar
   certo), nao reordenar candidatos. As features mais fortes sao simples: margem
   entre o 1o e o 2o, e CONSENSO entre recuperadores independentes.

O limiar entra por folds internos (nested), como no restante da Fase 2.

Uso (da pasta fase2/):
    python -m src.confianca
"""
import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.config import ALVO_PRECISAO, ARTEFATOS, N_REPEATS, SEED
from src.dicionario import Dicionario, normalizar
from src.protocolo import (
    acerto,
    carregar_gold,
    carregar_questoes,
    estratos,
    folds_estratificados,
    grupos_duplicados,
    wilson,
)
from src.recuperacao import Busca, texto_questao, texto_tema
from src.temas import Arvore

RETRIEVERS = ["rrf_all", "tfidf_char", "tfidf", "bm25"]
MAPAD = {"Direito Penal": "Penal", "Penal": "Penal",
         "Direito Processual Penal": "Processo Penal", "Processo Penal": "Processo Penal",
         "Direito Penal - Legislação Especial": "Direito Penal - Legislação Especial"}


def promover(arv, t):
    """Regra do pai: nivel 2 -> tema pai (se publicavel)."""
    if arv.nivel.get(t, 0) == 2:
        p = arv.parent.get(t)
        if p and arv.publicavel(p):
            return p
    return t


def scores_arvore(arv, pool, M, temas1):
    """Score de cada tema (nivel 1) = max da similaridade sobre a subarvore."""
    idx = {t: j for j, t in enumerate(pool)}
    Mp = np.zeros((M.shape[0], len(temas1)))
    for c, t in enumerate(temas1):
        cols = [idx[t]] + [idx[x] for x in arv.filhos.get(t, []) if x in idx]
        Mp[:, c] = M[:, cols].max(axis=1)
    return Mp


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    ids = list(gold.index)
    qmap = q.set_index("id")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    temas1 = [t for t in arv.ativos.tema_id if arv.nivel[t] == 1]
    busca = Busca([texto_tema(arv, t) for t in pool])
    q_texts = [texto_questao(qmap.loc[i]) for i in ids]
    dic = Dicionario()
    gemeos = arv.gemeos()
    max_nq = max(arv.nq.get(t, 0) for t in pool) or 1

    Ms = {r: busca.scores(r, q_texts) for r in RETRIEVERS}
    Mps = {r: scores_arvore(arv, pool, Ms[r], temas1) for r in RETRIEVERS}
    prim = RETRIEVERS[0]

    linhas, y, pred = [], [], []
    for i, qid in enumerate(ids):
        alvos = gold.loc[qid, "alvos"]
        row = qmap.loc[qid]
        M, Mp = Ms[prim], Mps[prim]
        o = np.argsort(-M[i])
        t1_pool = pool[o[0]]
        pred_i = promover(arv, t1_pool)
        tops = {}
        for r in RETRIEVERS:
            rr = np.argsort(-Ms[r][i])
            t1r = pool[rr[0]]
            tops[r] = promover(arv, t1r)
            row[f"rel_{r}"] = float(Ms[r][i, rr[0]] / (Ms[r][i, rr[0]] + Ms[r][i, rr[1]] + 1e-12))
        ob = np.argsort(-Mp[i])
        bs1, bs2 = float(Mp[i, ob[0]]), float(Mp[i, ob[1]])
        s1, s2 = float(M[i, o[0]]), float(M[i, o[1]])
        _, chaves = dic.casamentos(row["texto"])
        termos_lei = [normalizar(e["termos"]) for e in dic.entradas if e["chave"] in chaves]
        texto_p = normalizar(texto_tema(arv, pred_i))
        disc = MAPAD.get(row["disciplina_origem"], "__sem__")
        feats = {
            "rel_pri": row[f"rel_{prim}"],
            "gap_pri": (s1 - s2) / s1 if s1 > 0 else 0.0,
            "rel_char": row["rel_tfidf_char"],
            "rel_tfidf": row["rel_tfidf"],
            "rel_bm25": row["rel_bm25"],
            "consenso_top1": sum(1 for r in RETRIEVERS if tops[r] == pred_i) / len(RETRIEVERS),
            "branch_rel": bs1 / (bs1 + bs2) if (bs1 + bs2) > 0 else 0.5,
            "branch_gap": (bs1 - bs2) / bs1 if bs1 > 0 else 0.0,
            "nivel_top1": float(arv.nivel.get(t1_pool, 0)),
            "disc_match": float(disc != "__sem__" and arv.raiz(pred_i) == disc),
            "log_nq": float(np.log1p(arv.nq.get(pred_i, 0)) / np.log1p(max_nq)),
            "is_gemeo": float(pred_i in gemeos),
            "lei_match": float(any(termo and termo in texto_p for termo in termos_lei)),
        }
        linhas.append(feats)
        y.append(1 if acerto(arv, alvos, pred_i) else 0)
        pred.append(pred_i)

    X = pd.DataFrame(linhas)
    y = np.array(y)
    X.to_csv(ARTEFATOS / "confianca_features.csv", index=False)

    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids])
    est = estratos(gold)
    folds = []
    for r in range(N_REPEATS):
        folds += folds_estratificados(est, grupos, n_splits=5, seed=SEED + r)

    def fit_pred(tr, te, seed=SEED):
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", random_state=seed))
        clf.fit(X.iloc[tr], y[tr])
        return clf.predict_proba(X.iloc[te])[:, 1]

    # OOF (predicao honesta) e tau aninhado
    oof = np.full(len(y), np.nan)
    pubs = np.zeros(len(y), dtype=bool)
    for tr, te in folds:
        tr_set = set(int(i) for i in tr)
        inner = {}
        for tr2, te2 in folds:
            st = [int(i) for i in tr2 if int(i) in tr_set]
            se = [int(i) for i in te2 if int(i) in tr_set]
            if not st or not se:
                continue
            inner.update(dict(zip(se, fit_pred(st, se))))
        # tau: maior cobertura com precisao >= alvo nos folds internos
        tau = None
        melhor = -1
        for t in sorted(set(inner.values()), reverse=True):
            sel = [i for i, p in inner.items() if p >= t]
            if not sel:
                continue
            ac = sum(int(y[i]) for i in sel)
            if ac / len(sel) >= ALVO_PRECISAO and len(sel) > melhor:
                melhor, tau = len(sel), t
        p_te = fit_pred(list(tr_set), [int(i) for i in te])
        for j, i in enumerate(te):
            oof[int(i)] = p_te[j] if np.isnan(oof[int(i)]) else max(oof[int(i)], p_te[j])
            if tau is not None and p_te[j] >= tau:
                pubs[int(i)] = True

    ac_all = int(y.sum())
    lo, hi = wilson(ac_all, len(y))
    pub_ac = int(y[pubs].sum())
    lo2, hi2 = wilson(pub_ac, int(pubs.sum()))

    # curva com o score OOF (ordenacao por confianca)
    grade = sorted(set(np.round(oof, 4)), reverse=True)
    curva = []
    for t in grade:
        sel = oof >= t
        m = int(sel.sum())
        if not m:
            continue
        ac = int(y[sel].sum())
        lo3, hi3 = wilson(ac, m)
        curva.append({"limiar": t, "publicados": m, "acertos": ac, "precisao": ac / m,
                      "precisao_lo": lo3, "cobertura": m / len(y)})

    res = {
        "publicando_tudo_com_pai": {
            "acertos": ac_all, "n": len(y), "precisao": round(ac_all / len(y), 4),
            "precisao_lo": round(lo, 4),
        },
        "com_limiar_aninhado": {
            "publicados": int(pubs.sum()), "acertos": pub_ac,
            "precisao": round(pub_ac / max(pubs.sum(), 1), 4),
            "precisao_lo": round(lo2, 4), "cobertura": round(pubs.sum() / len(y), 4),
        },
        "features": list(X.columns),
    }
    (ARTEFATOS / "confianca_resumo.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(curva).to_csv(ARTEFATOS / "confianca_curva.csv", index=False)
    pd.DataFrame(
        {
            "qid": ids,
            "pred": pred,
            "p_oof": np.round(oof, 4),
            "correto": y,
            "fora": gold["fora"].astype(int).values,
            "disciplina_origem": [qmap.loc[i, "disciplina_origem"] for i in ids],
        }
    ).to_csv(ARTEFATOS / "confianca_oof.csv", index=False)

    print("=== confianca no nivel da questao (promovendo top-1 nivel2 -> pai) ===")
    print(f"publicando tudo: {ac_all}/{len(y)} = {ac_all/len(y):.3f} [lo={lo:.3f}]")
    print(f"com limiar (nested): {pub_ac}/{int(pubs.sum())} = {pub_ac/max(pubs.sum(),1):.3f} [lo={lo2:.3f}] "
          f"cobertura={pubs.sum()/len(y):.3f}")
    cv = pd.DataFrame(curva)
    print("\ncurva (melhor precisao por cobertura minima):")
    for alvo_cob in (0.1, 0.2, 0.3, 0.4, 0.5):
        sub = cv[cv.cobertura >= alvo_cob]
        if len(sub):
            b = sub.loc[sub.precisao.idxmax()]
            print(f"  cob>={alvo_cob:.1f}: precisao={b.precisao:.2f} [{b.precisao_lo:.2f}] em cob={b.cobertura:.2f} (pub={int(b.publicados)})")


if __name__ == "__main__":
    main()
