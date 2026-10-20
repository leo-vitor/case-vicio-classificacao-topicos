"""Etapa 3 — Reranker de candidatos (regressao logistica) com validacao aninhada.

Ideia: o top-1 do TF-IDF decide por similaridade bruta. O reranker olha *features do
candidato* (posicao, margem, relacao hierarquica com o top-1, disciplina, lei citada,
prior do tema) e estima P(candidato correto). A decisao de publicar usa o maximo
dessas probabilidades.

Ponto metodologico central: a unidade de inferencia e a QUESTAO, nao o par. Os folds
separam questoes inteiras e o limiar de publicacao e escolhido em um nivel INTERNO de
folds (nested), para nao ver o conjunto que mede.

Uso (da pasta fase2/):
    python -m src.reranker                 # roda tfidf_char e rrf_all
    python -m src.reranker --recuperador rrf_all
"""
import argparse
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

MAPA_DISC = {
    "Direito Penal": "Penal",
    "Penal": "Penal",
    "Direito Processual Penal": "Processo Penal",
    "Processo Penal": "Processo Penal",
    "Direito Penal - Legislação Especial": "Direito Penal - Legislação Especial",
}

FEATURES = [
    "s_norm", "gap", "inv_rank", "rank_norm", "is_top1",
    "is_pai_top1", "is_filho_top1", "hier_top1", "mesmo_ramo_top1",
    "hier_top2", "mesmo_ramo_top2", "nivel1", "log_nq",
    "disc_match", "is_gemeo", "lei_match",
]


def candidatos(arv, pool, ordem, k, top_pais=5, top_filhos=3):
    """Top-k + pais dos primeiros + filhos dos primeiros temas de nivel 1."""
    C = [pool[j] for j in ordem[:k]]
    for t in C[:top_pais]:
        p = arv.parent.get(t)
        if p and arv.publicavel(p) and p not in C:
            C.append(p)
    for t in C[:top_filhos]:
        if arv.nivel.get(t) == 1:
            for c in arv.filhos.get(t, []):
                if arv.publicavel(c) and c not in C:
                    C.append(c)
    return C


def features_questao(arv, Mq, pool, C, qrow, dic, max_nq, gemeos):
    ordem = np.argsort(-Mq)
    rank = {pool[j]: r for r, j in enumerate(ordem)}
    pos = {t: j for j, t in enumerate(pool)}
    idx_top1, idx_top2 = ordem[0], ordem[1]
    top1, top2 = pool[idx_top1], pool[idx_top2]
    s1 = float(Mq[idx_top1])
    _, chaves = dic.casamentos(qrow["texto"])
    termos_lei = [normalizar(e["termos"]) for e in dic.entradas if e["chave"] in chaves]
    disc = MAPA_DISC.get(qrow["disciplina_origem"], "__sem__")

    linhas = []
    for t in C:
        s = float(Mq[pos[t]])
        r = rank[t]
        texto_t = normalizar(texto_tema(arv, t))
        linhas.append(
            [
                s / s1 if s1 > 0 else 0.0,
                (s1 - s) / s1 if s1 > 0 else 0.0,
                1.0 / (1.0 + r),
                r / max(len(ordem), 1),
                float(t == top1),
                float(arv.parent.get(top1) == t),
                float(t in arv.filhos.get(top1, [])),
                2.0 if t == top1 else (1.0 if arv.relacionado(t, top1) else 0.0),
                float(arv.raiz(t) == arv.raiz(top1)),
                2.0 if t == top2 else (1.0 if arv.relacionado(t, top2) else 0.0),
                float(arv.raiz(t) == arv.raiz(top2)),
                float(arv.nivel.get(t, 0) == 1),
                float(np.log1p(arv.nq.get(t, 0)) / np.log1p(max_nq)),
                float(disc != "__sem__" and arv.raiz(t) == disc),
                float(t in gemeos),
                float(any(termo and termo in texto_t for termo in termos_lei)),
            ]
        )
    return np.array(linhas, dtype=float)


def preparar(arv, busca, retriever, q_texts, ids, gold, qmap, dic, k):
    M = busca.scores(retriever, q_texts)
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    max_nq = max(arv.nq.get(t, 0) for t in pool) or 1
    gemeos = arv.gemeos()
    dados = []
    for i, qid in enumerate(ids):
        C = candidatos(arv, pool, np.argsort(-M[i]), k)
        X = features_questao(arv, M[i], pool, C, qmap.loc[qid], dic, max_nq, gemeos)
        alvos = list(gold.loc[qid, "alvos"])
        y = np.array([1 if acerto(arv, alvos, t) else 0 for t in C])
        dados.append({"qid": qid, "X": X, "C": C, "y": y, "alvos": alvos})
    return dados


def _empilhar(dados, idxs):
    X = np.vstack([dados[i]["X"] for i in idxs])
    y = np.concatenate([dados[i]["y"] for i in idxs])
    return X, y


def _modelo(seed=SEED):
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.5, max_iter=2000, class_weight="balanced", random_state=seed),
    )


def fit_predict(dados, treino, teste):
    X, y = _empilhar(dados, treino)
    if len(set(y)) < 2:
        return {}
    clf = _modelo().fit(X, y)
    saida = {}
    for i in teste:
        p = clf.predict_proba(dados[i]["X"])[:, 1]
        j = int(np.argmax(p))
        saida[i] = {"pred": dados[i]["C"][j], "p": float(p[j])}
    return saida


def escolher_tau(inner, alvo, criterio="ponto"):
    """Maior cobertura com precisao >= alvo nos dados de calibracao (folds internos)."""
    ps = sorted({v["p"] for v in inner.values()}, reverse=True)
    melhor_t, melhor_cob = None, -1
    for t in ps:
        pub = [v for v in inner.values() if v["p"] >= t]
        if not pub:
            continue
        ac = sum(1 for v in pub if v["correto"])
        m = len(pub)
        ok = (wilson(ac, m)[0] >= alvo) if criterio == "wilson" else (ac / m >= alvo)
        if ok and m > melhor_cob:
            melhor_cob, melhor_t = m, t
    return melhor_t


def avaliar(arv, dados, folds, alvo=ALVO_PRECISAO, criterio="ponto"):
    """Validacao aninhada: para cada fold externo, o limiar vem dos folds internos."""
    resultados = []
    for tr, te in folds:
        tr_set = set(int(i) for i in tr)
        te_list = [int(i) for i in te]
        inner = {}
        for tr2, te2 in folds:
            sub_tr = [int(i) for i in tr2 if int(i) in tr_set]
            sub_te = [int(i) for i in te2 if int(i) in tr_set]
            if not sub_te or not sub_tr:
                continue
            for i, v in fit_predict(dados, sub_tr, sub_te).items():
                v["correto"] = acerto(arv, dados[i]["alvos"], v["pred"])
                inner[i] = v
        tau = escolher_tau(inner, alvo, criterio)
        preds_te = fit_predict(dados, list(tr_set), te_list)
        for i, v in preds_te.items():
            v["correto"] = acerto(arv, dados[i]["alvos"], v["pred"])
            v["publica"] = bool(tau is not None and v["p"] >= tau)
            v["tau"] = tau
        resultados.append({"fold": (tr, te), "preds": preds_te, "tau": tau, "inner": inner})
    return resultados


def agregar(arv, dados, resultados, min_frac=0.5):
    """Cada questao e prevista por 5 modelos que nao a viram (repeticoes do CV).

    Publica se a maioria das repeticoes publicaria; o tema e o mais votado.
    """
    acum = {}
    for r in resultados:
        for i, v in r["preds"].items():
            v = dict(v)
            v["publica"] = bool(r["tau"] is not None and v["p"] >= r["tau"])
            acum.setdefault(i, []).append(v)
    linhas = []
    for i, vs in acum.items():
        frac = sum(v["publica"] for v in vs) / len(vs)
        preds = [v["pred"] for v in vs]
        pred = max(set(preds), key=preds.count)
        linhas.append(
            {
                "qid": dados[i]["qid"],
                "n_rep": len(vs),
                "pub_frac": round(frac, 3),
                "publica": frac >= min_frac,
                "pred": pred,
                "p_media": float(np.mean([v["p"] for v in vs])),
                "correto": bool(acerto(arv, dados[i]["alvos"], pred)),
                "fora": not dados[i]["alvos"],
            }
        )
    return pd.DataFrame(linhas)


def metricas(linhas):
    pub = linhas[linhas.publica]
    m, ac = len(pub), int(pub.correto.sum())
    lo, hi = wilson(ac, m)
    return {
        "publicados": m,
        "acertos": ac,
        "precisao": round(ac / m, 4) if m else None,
        "precisao_lo": round(lo, 4),
        "precisao_hi": round(hi, 4),
        "cobertura": round(m / len(linhas), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recuperador", nargs="*", default=["tfidf_char", "rrf_all"])
    ap.add_argument("--k", type=int, default=20)
    args = ap.parse_args()

    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    ids = list(gold.index)
    qmap = q.set_index("id")
    q_texts = [texto_questao(qmap.loc[i]) for i in ids]
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    busca = Busca([texto_tema(arv, t) for t in pool])
    dic = Dicionario()
    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids])
    est = estratos(gold)
    folds = []
    for r in range(N_REPEATS):
        folds += folds_estratificados(est, grupos, n_splits=5, seed=SEED + r)

    saida = {}
    for retriever in args.recuperador:
        dados = preparar(arv, busca, retriever, q_texts, ids, gold, qmap, dic, args.k)
        res = avaliar(arv, dados, folds, criterio="ponto")
        linhas = agregar(arv, dados, res)
        linhas.to_csv(ARTEFATOS / f"reranker_{retriever}_predicoes.csv", index=False)
        # teto: publicando todo mundo (argmax), qual a precisao?
        teto = metricas(linhas.assign(publica=True))
        op = metricas(linhas)
        saida[retriever] = {"argmax_sem_limiar": teto, "com_limiar": op}
        print(f"\n=== reranker {retriever} (k={args.k}) ===")
        print(f"  argmax sem limiar : {teto['acertos']}/{len(linhas)} = {teto['precisao']:.3f} "
              f"[{teto['precisao_lo']:.3f}-{teto['precisao_hi']:.3f}]")
        print(f"  com limiar (ponto): {op['acertos']}/{op['publicados']} = {op['precisao']} "
              f"[{op['precisao_lo']}-{op['precisao_hi']}] cobertura={op['cobertura']}")

    (ARTEFATOS / "reranker_resumo.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
