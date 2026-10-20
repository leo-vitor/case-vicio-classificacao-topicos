"""Etapa 1 — Baseline lexical (A0/A1) com protocolo honesto.

O que este script responde:
  1. O tema certo (ou um no relacionado) aparece entre os k primeiros? Em que k?
  2. Variando o limiar de confianca no top-1, qual a curva precisao x cobertura?
  3. Escolhendo o limiar FORA da dobra, qual a precisao/cobertura que se sustenta?

Nada aqui chama LLM. Tudo roda em segundos.

Uso (da pasta fase2/):
    python -m src.baseline                 # roda tudo, imprime e salva em artefatos/
    python -m src.baseline --dic           # enriquece a consulta com o dicionario
"""
import argparse
import json

import numpy as np
import pandas as pd

from src.config import ARTEFATOS, N_REPEATS, SEED, TOP_K
from src.dicionario import Dicionario
from src.protocolo import (
    acerto,
    carregar_gold,
    carregar_questoes,
    curva,
    estratos,
    folds_estratificados,
    grupos_duplicados,
    ponto_oof,
    wilson,
)
from src.recuperacao import RETRIEVERS, Busca, sinais, texto_questao, texto_tema
from src.temas import Arvore

KS = [1, 3, 5, 10, 20]
SINAIS = ["rel", "gap", "abs"]


def recall(busca, M, pool, arv, gold, ids, ks=KS):
    """recall@k exato e hierarquico (teto do juiz). Fora-da-taxonomia nao entra."""
    idx_alvo = {t: j for j, t in enumerate(pool)}
    linhas = []
    validos = [i for i, qid in enumerate(ids) if not gold.loc[qid, "fora"]]
    n = len(validos)
    for k in ks:
        exato = hier = 0
        for i in validos:
            qid = ids[i]
            alvos = gold.loc[qid, "alvos"]
            topo = [pool[j] for j in np.argsort(-M[i])[:k]]
            if any(t in topo for t in alvos):
                exato += 1
            if any(arv.relacionado(p, t) for p in topo for t in alvos):
                hier += 1
        linhas.append({"k": k, "n": n, "recall_exato": exato / n, "recall_hier": hier / n})
    return pd.DataFrame(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dic", action="store_true", help="enriquece a consulta com o dicionario")
    ap.add_argument("--k", type=int, default=TOP_K)
    args = ap.parse_args()

    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    ids = list(gold.index)
    qmap = q.set_index("id")

    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    t_texts = [texto_tema(arv, t) for t in pool]

    dic = Dicionario()
    q_texts = [texto_questao(qmap.loc[i]) for i in ids]
    if args.dic:
        q_texts = [dic.expandir(t) for t in q_texts]

    busca = Busca(t_texts)

    # ---- diagnostico do gold
    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids])
    n_grupos_dup = len(set(grupos))
    est = estratos(gold)
    # Folds compartilhados por TODOS os metodos; cada repeticao usa uma seed derivada.
    folds = []
    for r in range(N_REPEATS):
        folds += folds_estratificados(est, grupos, n_splits=5, seed=SEED + r)

    diag = {
        "n_gold": len(ids),
        "fora": int(gold["fora"].sum()),
        "com_extras": int((gold["extras"].map(len) > 0).sum()),
        "temas_centrais_distintos": int(gold["tema_central_id"].replace("", np.nan).nunique()),
        "grupos_near_duplicate": n_grupos_dup,
        "estratos": pd.Series(est).value_counts().to_dict(),
        "por_faixa": gold["faixa"].value_counts().to_dict(),
        "dic_versao": dic.versao(),
        "dic_entradas": len(dic.entradas),
        "n_folds": len(folds),
    }

    recs, curvas, pontos = [], [], []
    for retriever in RETRIEVERS:
        M = busca.scores(retriever, q_texts)
        r = recall(busca, M, pool, arv, gold, ids, KS)
        r.insert(0, "recuperador", retriever)
        recs.append(r)

        corretos = np.array(
            [acerto(arv, gold.loc[i, "alvos"], pool[sinais(M, j)["idx_top1"]]) for j, i in enumerate(ids)],
            dtype=bool,
        )
        for s in SINAIS:
            sc = np.array([sinais(M, j)[s] for j in range(len(ids))])
            cv = curva(sc, corretos)
            cv.insert(0, "sinal", s)
            cv.insert(0, "recuperador", retriever)
            curvas.append(cv)
            for criterio in ("wilson", "ponto"):
                p = ponto_oof(sc, corretos, folds, criterio=criterio)
                pontos.append(
                    {
                        "recuperador": retriever,
                        "sinal": s,
                        "criterio": criterio,
                        "publicados": p["publicados"],
                        "acertos": p["acertos"],
                        "precisao": round(p["precisao"], 4) if p["publicados"] else None,
                        "precisao_lo": round(p["precisao_lo"], 4),
                        "precisao_hi": round(p["precisao_hi"], 4),
                        "cobertura": round(p["cobertura"], 4),
                        "limiares": [None if not np.isfinite(x) else round(x, 4) for x in p["limiares_por_fold"]],
                    }
                )

    rec_df = pd.concat(recs, ignore_index=True)
    cv_df = pd.concat(curvas, ignore_index=True)
    rec_df.to_csv(ARTEFATOS / "recuperacao.csv", index=False)
    cv_df.to_csv(ARTEFATOS / "curva_precisao_cobertura.csv", index=False)
    (ARTEFATOS / "diagnostico_gold.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ARTEFATOS / "ponto_operacao_oof.json").write_text(
        json.dumps(pontos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- saida legivel
    print("=== diagnostico do gold (100) ===")
    print(json.dumps(diag, ensure_ascii=False, indent=2))
    print("\n=== recall@k (n = 92 com tema; 8 fora) ===")
    for retriever in RETRIEVERS:
        sub = rec_df[rec_df.recuperador == retriever]
        linha = "  ".join(
            f"k={r.k}: exato={r.recall_exato:.2f}/hier={r.recall_hier:.2f}" for r in sub.itertuples()
        )
        print(f"{retriever:16s} {linha}")

    print("\n=== ponto de operacao (limiar escolhido fora da dobra) ===")
    pt = pd.DataFrame(pontos)
    pt["precisao"] = pt["precisao"].astype(float)
    print(
        pt.sort_values(["criterio", "cobertura"], ascending=[True, False])
        .head(20)
        .to_string(index=False)
    )
    pt.to_csv(ARTEFATOS / "ponto_operacao_oof.csv", index=False)

    print("\nMelhores (precisao_lo >= 0.95 e maior cobertura):")
    bons = pt[pt.publicados > 0].query("precisao_lo >= 0.95")
    print(bons.sort_values("cobertura", ascending=False).head(10).to_string(index=False) if len(bons) else "  (nenhum)")
    print(f"\nArtefatos salvos em {ARTEFATOS}")


if __name__ == "__main__":
    main()
