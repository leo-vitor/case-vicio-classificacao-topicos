"""Carrega a base de desenvolvimento da Fase 2 uma unica vez.

Contem: arvore, gabarito (100), features do modelo de confianca, probabilidade
fora da dobra (`p_oof`) e os folds agrupados compartilhados por todos os metodos.

Fica separado para que `conformal.py` e `auditoria.py` usem exatamente a mesma
base — e para que ninguem recompute a matriz de similaridade com folds diferentes.
"""
import numpy as np

from src.config import N_REPEATS, SEED
from src.decisao import RETRIEVERS, PRIM, features as features_q, oof_probs, scores_temas
from src.enriquecimento import carregar as carregar_artefato
from src.enriquecimento import textos as textos_enriquecidos
from src.protocolo import (
    acerto,
    carregar_gold,
    carregar_questoes,
    estratos,
    folds_estratificados,
    grupos_duplicados,
)
from src.recuperacao import Busca, texto_questao
from src.temas import Arvore


def tema1(arv, t):
    """Tema de nivel 1 do no (ele mesmo, se ja for nivel 1). None se nao der."""
    n = arv.nivel.get(t, 0)
    if n == 1:
        return t
    if n == 2:
        p = arv.parent.get(t)
        return p if (p and arv.nivel.get(p) == 1) else None
    return None


def base():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    ids = list(gold.index)
    qmap = q.set_index("id")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    temas1 = [t for t in arv.ativos.tema_id if arv.nivel[t] == 1]
    busca = Busca(textos_enriquecidos(arv, pool, carregar_artefato()))
    gemeos = arv.gemeos()
    max_nq = max(arv.nq.get(t, 0) for t in pool) or 1

    qt = [texto_questao(qmap.loc[i]) for i in ids]
    Ms = {r: busca.scores(r, qt) for r in RETRIEVERS}
    Mps = {r: scores_temas(arv, pool, Ms[r], temas1) for r in RETRIEVERS}

    X, pred, cons = features_q(arv, qmap, ids, Ms, Mps, pool, gemeos, max_nq)
    y = np.array([1 if acerto(arv, gold.loc[i, "alvos"], p) else 0 for i, p in zip(ids, pred)])

    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids])
    est = estratos(gold)
    folds = []
    for r in range(N_REPEATS):
        folds += folds_estratificados(est, grupos, n_splits=5, seed=SEED + r)

    return {
        "arv": arv, "gold": gold, "ids": ids, "pool": pool, "temas1": temas1,
        "X": X, "y": y, "pred": pred, "cons": np.asarray(cons, dtype=float),
        "p_oof": oof_probs(X, y, folds), "folds": folds, "M": Ms[PRIM],
        "Ms": Ms, "qmap": qmap,
    }
