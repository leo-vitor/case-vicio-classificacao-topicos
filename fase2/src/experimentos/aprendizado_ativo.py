"""Simulacao de aprendizado ativo na folha-verdade.

Nao altera o modelo. Para cada semente, separa 40 questoes de teste e 60 de pool,
comeca com 20 rotulos e simula a adicao de 10, 20 ou 40 rotulos. O limiar de cada
estado e escolhido por validacao interna de 5 dobras no conjunto rotulado; o teste
nunca entra no treino nem na escolha do limiar.

Uso, da pasta fase2/:
    python -m src.experimentos.aprendizado_ativo
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit

from src.artefato import base
from src.config import ALVO_PRECISAO, ARTEFATOS
from src.decisao import escolher_regra, modelo
from src.protocolo import acerto, wilson


OUT = ARTEFATOS / "experimentos"
SEEDS = list(range(30))
BUDGETS = [10, 20, 40]
INICIAL = 20
TESTE = 40
ESTRATEGIAS = ["acaso", "limiar", "evidencia", "legislacao"]


def split_teste_pool(y_estrato, rng, n_teste=TESTE):
    """Split estratificado simples; devolve indices de pool e teste."""
    idx = np.arange(len(y_estrato))
    teste = []
    for e in sorted(set(y_estrato)):
        g = idx[[i for i in idx if y_estrato[i] == e]]
        rng.shuffle(g)
        n = int(round(n_teste * len(g) / len(y_estrato)))
        n = max(1, min(len(g) - 1, n))
        teste.extend(g[:n].tolist())
    teste = sorted(set(teste))
    # Ajuste de tamanho: completa ou remove pelo maior estrato.
    while len(teste) < n_teste:
        faltam = [i for i in idx if i not in set(teste)]
        if not faltam:
            break
        teste.append(int(rng.choice(faltam)))
    if len(teste) > n_teste:
        rng.shuffle(teste)
        teste = sorted(teste[:n_teste])
    pool = [i for i in idx if i not in set(teste)]
    return np.array(pool), np.array(teste)


def estado(X, y, cons, labeled, seed):
    """Treina no conjunto rotulado, escolhe limiar por CV interna e devolve estado."""
    labeled = np.array(sorted(labeled))
    Xl, yl, cl = X.iloc[labeled], y[labeled], cons[labeled]
    classes, counts = np.unique(yl, return_counts=True)
    if len(classes) < 2:
        return {"tau": None, "c": None, "p": None, "modelo": None}
    n_splits = min(5, int(counts.min()))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    p_oof = np.zeros(len(labeled))
    for tr, te in skf.split(Xl, yl):
        clf = modelo().fit(Xl.iloc[tr], yl[tr])
        p_oof[te] = clf.predict_proba(Xl.iloc[te])[:, 1]
    tau, c = escolher_regra(p_oof, cl, yl, ALVO_PRECISAO)
    if tau is None:
        tau, c = 0.5, 1.0
    clf = modelo().fit(Xl, yl)
    p_all = clf.predict_proba(X)[:, 1]
    return {"tau": float(tau), "c": float(c), "p": p_all, "modelo": clf}


def metricas(estado_, cons, y, teste, arv, gold, ids):
    if estado_["p"] is None:
        return {"publicados": 0, "acertos": 0, "precisao": 0.0,
                "cobertura": 0.0, "wilson": [0.0, 1.0]}
    pub = (cons[teste] >= estado_["c"]) & (estado_["p"][teste] >= estado_["tau"])
    m = int(pub.sum())
    ac = 0
    for j, i in enumerate(teste):
        if not pub[j]:
            continue
        qid = ids[i]
        if acerto(arv, gold.loc[qid, "alvos"], None):
            ac += 1
    # acerto nao depende de pred: a publicacao usa o top-1, que esta em pred.
    # O chamador passa pred em estado_["pred"] para evitar depender do texto.
    ac = int(sum(1 for j, i in enumerate(teste) if pub[j] and estado_["pred"][i]))
    lo, hi = wilson(ac, m)
    return {"publicados": m, "acertos": ac,
            "precisao": round(ac / m, 4) if m else None,
            "cobertura": round(m / len(teste), 4),
            "wilson": [round(float(lo), 4), round(float(hi), 4)] if m else [0.0, 1.0]}


def escolher(estrategia, restantes, estado_, cons, y, pred, unique_ev, le, rng, n=10):
    restantes = list(restantes)
    if not restantes:
        return []
    if estrategia == "acaso":
        return rng.choice(restantes, size=min(n, len(restantes)), replace=False).tolist()
    if estrategia == "limiar":
        if estado_["p"] is None:
            score = np.zeros(len(restantes))
        else:
            tau = estado_["tau"]
            score = -np.abs(estado_["p"][restantes] - tau)
        ordem = np.argsort(-score, kind="stable")
        return [restantes[i] for i in ordem[:n]]
    if estrategia == "evidencia":
        # Primeiro as questoes com ramo unico de evidencia; dentro do grupo,
        # sorteio para nao usar o gabarito.
        grupo = [i for i in restantes if unique_ev[i]]
        if len(grupo) >= n:
            return rng.choice(grupo, size=n, replace=False).tolist()
        resto = [i for i in restantes if i not in set(grupo)]
        escolhidos = grupo + rng.choice(resto, size=min(n - len(grupo), len(resto)),
                                        replace=False).tolist()
        return escolhidos[:n]
    if estrategia == "legislacao":
        grupo = [i for i in restantes if le[i]]
        if len(grupo) >= n:
            return rng.choice(grupo, size=n, replace=False).tolist()
        resto = [i for i in restantes if i not in set(grupo)]
        escolhidos = grupo + rng.choice(resto, size=min(n - len(grupo), len(resto)),
                                        replace=False).tolist()
        return escolhidos[:n]
    raise ValueError(estrategia)


def main():
    b = base()
    arv, gold, ids, X, y, cons, pred = (
        b["arv"], b["gold"], b["ids"], b["X"], b["y"], b["cons"], b["pred"]
    )
    ev = pd.read_csv(OUT / "evidencia_legal.csv", dtype=str).fillna("").set_index("id")
    unique_ev = np.array([int(ev.loc[qid, "ramo_unico_geral"]) == 1 for qid in ids])
    le = np.array([arv.raiz(p) == "Direito Penal - Legislação Especial" for p in pred])
    y_correto = np.array([acerto(arv, gold.loc[qid, "alvos"], p) for qid, p in zip(ids, pred)])
    disciplina = list(gold["disciplina"])

    resultados = {s: {b_: [] for b_ in BUDGETS} for s in ESTRATEGIAS}
    seeds_usadas = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        pool, teste = split_teste_pool(disciplina, rng)
        if len(teste) < 20 or len(pool) < INICIAL + max(BUDGETS):
            continue
        # Conjunto inicial comum as quatro estrategias nesta semente.
        inicial = None
        for _ in range(100):
            cand = rng.choice(pool, size=INICIAL, replace=False)
            if len(np.unique(y[cand])) == 2:
                inicial = cand.tolist()
                break
        if inicial is None:
            continue
        seeds_usadas.append(seed)
        for estrategia in ESTRATEGIAS:
            labeled = list(inicial)
            restantes = [i for i in pool if i not in set(labeled)]
            for alvo in [0] + BUDGETS:
                if alvo in BUDGETS:
                    st = estado(X, y, cons, labeled, seed)
                    st["pred"] = y_correto
                    met = metricas(st, cons, y, teste, arv, gold, ids)
                    resultados[estrategia][alvo].append(met)
                if alvo == max(BUDGETS):
                    break
                st = estado(X, y, cons, labeled, seed)
                st["pred"] = y_correto
                novos = escolher(estrategia, restantes, st, cons, y, pred,
                                 unique_ev, le, rng, n=10)
                labeled.extend(novos)
                restantes = [i for i in restantes if i not in set(novos)]

    agregado = {}
    for s in ESTRATEGIAS:
        agregado[s] = {}
        for b_ in BUDGETS:
            ms = resultados[s][b_]
            if not ms:
                continue
            prec = np.array([m["precisao"] for m in ms if m["precisao"] is not None])
            cob = np.array([m["cobertura"] for m in ms])
            ac = int(sum(m["acertos"] for m in ms))
            pub = int(sum(m["publicados"] for m in ms))
            lo, hi = wilson(ac, pub)
            agregado[s][b_] = {
                "n_sementes": len(ms),
                "n_com_publicacao": int(len(prec)),
                "precisao_media": round(float(prec.mean()), 4) if len(prec) else None,
                "precisao_min": round(float(prec.min()), 4) if len(prec) else None,
                "precisao_max": round(float(prec.max()), 4) if len(prec) else None,
                "cobertura_media": round(float(cob.mean()), 4),
                "cobertura_min": round(float(cob.min()), 4),
                "cobertura_max": round(float(cob.max()), 4),
                "publicados_medios": round(float(np.mean([m["publicados"] for m in ms])), 2),
                "wilson_agregado": [round(float(lo), 4), round(float(hi), 4)],
            }

    # Pareado por semente contra "acaso": vitorias/empates/derrotas.
    pareado = {}
    for s in ESTRATEGIAS:
        if s == "acaso":
            continue
        pareado[s] = {}
        for b_ in BUDGETS:
            pares = [(m["precisao"], m2["precisao"])
                     for m, m2 in zip(resultados[s][b_], resultados["acaso"][b_])
                     if m["precisao"] is not None and m2["precisao"] is not None]
            if not pares:
                continue
            d = np.array([a - r for a, r in pares])
            cob = np.array([m["cobertura"] - m2["cobertura"]
                            for m, m2 in zip(resultados[s][b_], resultados["acaso"][b_])])
            pareado[s][b_] = {
                "n": len(d),
                "delta_medio": round(float(d.mean()), 4),
                "vitorias": int((d > 1e-12).sum()),
                "empates": int((np.abs(d) <= 1e-12).sum()),
                "derrotas": int((d < -1e-12).sum()),
                "cobertura_delta_medio": round(float(cob.mean()), 4),
                "cobertura_vitorias": int((cob > 1e-12).sum()),
                "cobertura_empates": int((np.abs(cob) <= 1e-12).sum()),
                "cobertura_derrotas": int((cob < -1e-12).sum()),
            }

    saida = {"n_folha": len(ids), "sementes": seeds_usadas,
             "inicial": INICIAL, "teste": TESTE, "agregado": agregado,
             "pareado_precisao_vs_acaso": pareado}
    (OUT / "aprendizado_ativo.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    linhas = ["# Aprendizado ativo na folha", "",
              f"Sementes: {len(seeds_usadas)}; teste {TESTE}; inicio {INICIAL}; blocos de 10.",
              "", "| estrategia | +rotulos | precisao media (faixa) | cobertura media (faixa) | Wilson agregado |",
              "|---|---:|---|---|---|"]
    for s in ESTRATEGIAS:
        for b_ in BUDGETS:
            m = agregado[s].get(b_)
            if not m:
                continue
            if m["precisao_media"] is None:
                prec_txt = "sem publicacao"
            else:
                prec_txt = (f"{m['precisao_media']:.2f} "
                            f"({m['precisao_min']:.2f}-{m['precisao_max']:.2f})")
            linhas.append(
                f"| {s} | +{b_} | {prec_txt} | "
                f"{m['cobertura_media']:.2f} "
                f"({m['cobertura_min']:.2f}-{m['cobertura_max']:.2f}) | "
                f"{m['wilson_agregado'][0]:.2f}-{m['wilson_agregado'][1]:.2f} |"
            )
    linhas += ["", "Pareado de precisao contra o acaso (vitorias/empates/derrotas):"]
    for s, d in pareado.items():
        for b_, x in d.items():
            linhas.append(f"- {s} +{b_}: {x['vitorias']}/{x['empates']}/{x['derrotas']} "
                          f"(delta medio {x['delta_medio']:+.3f})")
    (OUT / "aprendizado_ativo.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print(json.dumps({"n_sementes": len(seeds_usadas), "agregado": agregado,
                      "pareado": pareado}, ensure_ascii=False, indent=2))
    print(f"Saidas: {OUT / 'aprendizado_ativo.json'} e .md")


if __name__ == "__main__":
    main()
