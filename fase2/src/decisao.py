"""Etapa 4/5 — Decisao seletiva e geracao do publicacao.csv (sem LLM).

Encadeia o que foi validado nas etapas anteriores:

  1. Recuperacao lexical (rrf_all como primario; tfidf_char, tfidf e bm25 para consenso).
  2. Regra do pai: se o top-1 e subtema (nivel 2), publicar o TEMA pai (nunca piora).
  3. Confianca no nivel da questao (regressao logistica sobre features).
  4. Regra seletiva: publicar se confianca >= tau E consenso >= c.
     tau e c sao escolhidos FORA do grupo que mede (protocolo aninhado).
  5. `fora`: conservador — so com evidencia forte; na duvida, revisar.
  6. Escreve `publicacao.csv` para as 659 e resume a previsao.

Uso (da pasta fase2/):
    python -m src.decisao
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
PRIM = "rrf_all"
MAPAD = {"Direito Penal": "Penal", "Penal": "Penal",
         "Direito Processual Penal": "Processo Penal", "Processo Penal": "Processo Penal",
         "Direito Penal - Legislação Especial": "Direito Penal - Legislação Especial"}


def promover(arv, t):
    if arv.nivel.get(t, 0) == 2:
        p = arv.parent.get(t)
        if p and arv.publicavel(p):
            return p
    return t


def scores_temas(arv, pool, M, temas1):
    idx = {t: j for j, t in enumerate(pool)}
    Mp = np.zeros((M.shape[0], len(temas1)))
    for c, t in enumerate(temas1):
        cols = [idx[t]] + [idx[x] for x in arv.filhos.get(t, []) if x in idx]
        Mp[:, c] = M[:, cols].max(axis=1)
    return Mp


def features(arv, qmap, ids, Ms, Mps, pool, dic, gemeos, max_nq):
    rows, pred, cons = [], [], []
    for i, qid in enumerate(ids):
        row = qmap.loc[qid]
        M, Mp = Ms[PRIM], Mps[PRIM]
        o = np.argsort(-M[i])
        t1 = pool[o[0]]
        pi = promover(arv, t1)
        rels = {}
        tops = []
        for r in RETRIEVERS:
            rr = np.argsort(-Ms[r][i])
            rels[r] = float(Ms[r][i, rr[0]] / (Ms[r][i, rr[0]] + Ms[r][i, rr[1]] + 1e-12))
            tops.append(promover(arv, pool[rr[0]]))
        ob = np.argsort(-Mp[i])
        bs1, bs2 = float(Mp[i, ob[0]]), float(Mp[i, ob[1]])
        s1, s2 = float(M[i, o[0]]), float(M[i, o[1]])
        _, chaves = dic.casamentos(row["texto"])
        termos = [normalizar(e["termos"]) for e in dic.entradas if e["chave"] in chaves]
        tp = normalizar(texto_tema(arv, pi))
        disc = MAPAD.get(row["disciplina_origem"], "__sem__")
        c = sum(1 for t in tops if t == pi) / len(RETRIEVERS)
        rows.append({
            "rel_pri": rels[PRIM],
            "gap_pri": (s1 - s2) / s1 if s1 > 0 else 0.0,
            "rel_char": rels["tfidf_char"],
            "rel_tfidf": rels["tfidf"],
            "rel_bm25": rels["bm25"],
            "consenso_top1": c,
            "branch_rel": bs1 / (bs1 + bs2) if (bs1 + bs2) > 0 else 0.5,
            "branch_gap": (bs1 - bs2) / bs1 if bs1 > 0 else 0.0,
            "nivel_top1": float(arv.nivel.get(t1, 0)),
            "disc_match": float(disc != "__sem__" and arv.raiz(pi) == disc),
            "log_nq": float(np.log1p(arv.nq.get(pi, 0)) / np.log1p(max_nq)),
            "is_gemeo": float(pi in gemeos),
            "lei_match": float(any(t and t in tp for t in termos)),
            "s1": s1,
        })
        pred.append(pi)
        cons.append(c)
    return pd.DataFrame(rows), pred, cons


def modelo():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", random_state=SEED))


def oof_probs(X, y, folds):
    """Probabilidade fora da dobra; media das repeticoes em que a questao foi testada."""
    soma = np.zeros(len(y))
    cnt = np.zeros(len(y))
    for tr, te in folds:
        clf = modelo().fit(X.iloc[tr], y[tr])
        p = clf.predict_proba(X.iloc[te])[:, 1]
        soma[te] += p
        cnt[te] += 1
    return soma / np.maximum(cnt, 1)


def escolher_regra(p, cons, y, alvo, grade_cons=(1.0, 0.75, 0.5)):
    """Maior cobertura com precisao >= alvo. Devolve (tau, c) ou (None, None)."""
    melhor = (None, None, -1)
    for c in grade_cons:
        base = cons >= c
        for t in sorted(set(p[base]), reverse=True):
            sel = base & (p >= t)
            m = int(sel.sum())
            if m == 0:
                continue
            if y[sel].mean() >= alvo and m > melhor[2]:
                melhor = (float(t), c, m)
    return melhor[0], melhor[1]


def escolher_regra_conservadora(p, cons, y, alvo, min_pub):
    """Entre as regras com precisao >= alvo e n >= min_pub, a mais conservadora.

    Criterio: maior limiar (menos publicacoes, mais seguras). Protege contra o
    otimismo de escolher o limiar no mesmo conjunto que mede.
    """
    cands = []
    for c in (1.0, 0.75, 0.5):
        base = cons >= c
        for t in sorted(set(p[base])):
            sel = base & (p >= t)
            m = int(sel.sum())
            if m < min_pub:
                continue
            if y[sel].mean() >= alvo:
                cands.append((float(t), c, m))
    if not cands:
        return None, None
    return max(cands, key=lambda x: (x[0], -x[2]))[:2]


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    qmap = q.set_index("id")
    ids100 = list(gold.index)
    todos = list(q["id"])
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    temas1 = [t for t in arv.ativos.tema_id if arv.nivel[t] == 1]
    busca = Busca([texto_tema(arv, t) for t in pool])
    dic = Dicionario()
    gemeos = arv.gemeos()
    max_nq = max(arv.nq.get(t, 0) for t in pool) or 1

    def blocos(ids):
        qt = [texto_questao(qmap.loc[i]) for i in ids]
        Ms = {r: busca.scores(r, qt) for r in RETRIEVERS}
        Mps = {r: scores_temas(arv, pool, Ms[r], temas1) for r in RETRIEVERS}
        return features(arv, qmap, ids, Ms, Mps, pool, dic, gemeos, max_nq)

    X100, pred100, cons100 = blocos(ids100)
    cons100 = np.asarray(cons100, dtype=float)
    y100 = np.array([1 if acerto(arv, gold.loc[qid, "alvos"], p) else 0
                     for qid, p in zip(ids100, pred100)])

    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids100])
    est = estratos(gold)
    folds = []
    for r in range(N_REPEATS):
        folds += folds_estratificados(est, grupos, n_splits=5, seed=SEED + r)

    p_oof = oof_probs(X100, y100, folds)

    # Regra honesta: escolhe (tau, c) nos grupos que nao estao sendo medidos
    # Regra honesta: escolhe (tau, c) nos grupos que nao estao sendo medidos.
    # Usa a probabilidade OOF (media das repeticoes), que e a mesma grandeza usada
    # na decisao final — evita o ruido de olhar uma unica dobra por vez.
    publica = np.zeros(len(y100), dtype=bool)
    regras = []
    for tr, te in folds[:5]:  # uma particao externa (5 grupos)
        te_idx = np.array([int(i) for i in te])
        tr_idx = np.array([i for i in range(len(y100)) if i not in set(te_idx.tolist())])
        tau, c = escolher_regra(p_oof[tr_idx], cons100[tr_idx], y100[tr_idx], ALVO_PRECISAO)
        regras.append((tau, c))
        if tau is not None:
            publica[te_idx] |= (cons100[te_idx] >= c) & (p_oof[te_idx] >= tau)

    ac = int(y100[publica].sum())
    m = int(publica.sum())
    lo, hi = wilson(ac, m)

    # Regra final (para aplicar nas 659): entre as regras que sustentam 95% de
    # precisao com pelo menos 20 publicadas nos 100, a MAIS CONSERVADORA (maior
    # limiar). E deliberadamente pessimista: escolher o limiar no mesmo conjunto
    # que mede infla o numero, e com 100 rotulos isso pesa.
    MIN_PUB = 20
    tau_f, c_f = escolher_regra_conservadora(p_oof, cons100, y100, ALVO_PRECISAO, MIN_PUB)
    if tau_f is None:
        tau_f, c_f = 0.95, 1.0

    X_all, pred_all, cons_all = blocos(todos)
    clf = modelo().fit(X100, y100)
    p_all = clf.predict_proba(X_all)[:, 1]

    # Avaliacao in-sample da regra fixa (consenso>=c_f, p>=tau_f) nos 100
    sel100 = (cons100 >= c_f) & (p_oof >= tau_f)
    ac100 = int(y100[sel100].sum())
    m100 = int(sel100.sum())
    lo100, hi100 = wilson(ac100, m100)

    decisao, tema, motivo = [], [], []
    for i, qid in enumerate(todos):
        if (cons_all[i] >= c_f) and (p_all[i] >= tau_f):
            decisao.append("publicar"); tema.append(pred_all[i]); motivo.append("")
        else:
            decisao.append("revisar"); tema.append(pred_all[i])
            if cons_all[i] < c_f:
                motivo.append(f"recuperadores divergem (consenso {cons_all[i]:.2f})")
            else:
                motivo.append(f"confianca {p_all[i]:.2f} abaixo do limiar {tau_f:.2f}")

    pub_df = pd.DataFrame({
        "id": todos, "decisao": decisao, "tema_central_id": tema, "extras_ids": "",
        "confianca": [round(float(c), 2) for c in np.clip(p_all, 0.02, 0.99)], "motivo": motivo,
    })
    pub_df.to_csv(ARTEFATOS.parent / "publicacao.csv", index=False)

    faixa = np.where(q["id"].str[1:].astype(int) <= 359, "antiga", "nova")
    pd.DataFrame({"id": todos, "p": p_all, "consenso": cons_all, "pred": pred_all,
                  "decisao": decisao, "faixa": faixa}).to_csv(ARTEFATOS / "pontuacao_659.csv", index=False)

    resumo = {
        "regra": {"consenso_min": c_f, "tau": round(tau_f, 4), "min_publicadas_treino": MIN_PUB},
        "regras_por_fold_nested": [
            {"tau": None if t is None else round(t, 4), "consenso": c} for t, c in regras
        ],
        "avaliacao_aninhada_100": {
            "publicados": m, "acertos": ac, "precisao": round(ac / m, 4) if m else None,
            "precisao_lo": round(lo, 4), "precisao_hi": round(hi, 4),
            "cobertura": round(m / len(y100), 4),
        },
        "regra_fixa_in_sample_100": {
            "publicados": m100, "acertos": ac100,
            "precisao": round(ac100 / m100, 4) if m100 else None,
            "precisao_lo": round(lo100, 4), "precisao_hi": round(hi100, 4),
            "cobertura": round(m100 / len(y100), 4),
        },
        "publicando_tudo_100": {"acertos": int(y100.sum()), "precisao": round(y100.mean(), 4)},
        "decisoes_659": pd.Series(decisao).value_counts().to_dict(),
    }
    (ARTEFATOS / "decisao_resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame({"qid": ids100, "pred": pred100, "p_oof": np.round(p_oof, 4),
                  "consenso": cons100, "correto": y100}).to_csv(ARTEFATOS / "decisao_oof.csv", index=False)

    print("=== decisao ===")
    print(f"100 (nested)   : {ac}/{m} = {ac / m if m else float('nan'):.3f} [lo={lo:.3f}] cobertura={m/100:.3f}")
    print(f"100 (regra fixa): {ac100}/{m100} = {ac100 / m100 if m100 else float('nan'):.3f} "
          f"[lo={lo100:.3f}] cobertura={m100/100:.3f}  tau={tau_f:.3f}")
    print(f"decisoes nas 659: {resumo['decisoes_659']}")
    print(f"publicacao.csv -> {ARTEFATOS.parent / 'publicacao.csv'}")


if __name__ == "__main__":
    main()
