"""Experimento 2 — embeddings densos com temas enriquecidos (pré-registrado).

Pergunta: com o MESMO texto enriquecido nos temas, o embedding supera o `rrf_all`
no ramo@1? Duas variantes de prefixo (passage/query), sozinho e em fusão RRF.

Critério (escrito em docs/experimento_embeddings_v2.md antes da execução):
  adotar sse (a) ganho líquido >= 5 questões em 92 e (b) IC pareado 95% > 0.

Saídas:
  artefatos/embeddings_v2_por_questao.csv
  artefatos/embeddings_v2_resumo.csv
  artefatos/embeddings_v2_resumo.json

Uso (da pasta fase2/):
    .venv/bin/python -m src.embeddings_v2
"""
import hashlib
import json
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from src.artefato import base, tema1
from src.config import ARTEFATOS, RRF_K, SEED
from src.embeddings import MODELO_PADRAO, _hash, codificar
from src.enriquecimento import carregar as carregar_enr
from src.enriquecimento import textos as textos_enri
from src.pisos import bootstrap_delta
from src.protocolo import wilson
from src.recuperacao import _rrf_de_matrizes, ordem_desc

VARIANTS = ["emb_passage", "rrf_emb_passage", "emb_query", "rrf_emb_query"]
B = 2000


def info_top1(M, pool, arv, aceitos, alvos):
    """Top-1, ramo promovido (regra do pai), rank do primeiro ramo aceito e exato."""
    ordem = ordem_desc(M)
    t = pool[int(ordem[0])]
    br = tema1(arv, t)
    rank = None
    for pos, j in enumerate(ordem, start=1):
        if tema1(arv, pool[int(j)]) in aceitos:
            rank = pos
            break
    return {
        "top1": t,
        "branch": br,
        "rank": rank,
        "correct": bool(rank == 1),
        "exact": bool(t in alvos),
    }


def main():
    b = base()
    arv, gold, ids, pool = b["arv"], b["gold"], b["ids"], b["pool"]
    qmap, M_lex = b["qmap"], b["M"]
    n = len(ids)

    enr = carregar_enr()
    textos = textos_enri(arv, pool, enr)
    q_textos = [qmap.loc[i, "texto"] + " " + qmap.loc[i, "assunto_origem"] + " "
                + qmap.loc[i, "assunto_origem"] for i in ids]

    print(f"questoes: {n} | temas publicaveis: {len(pool)} | enriquecidos: {len(enr)}")
    print("codificando temas enriquecidos (passage/query)...", flush=True)
    Vt_pass = codificar(MODELO_PADRAO, "temas_enri_v2_passage", textos, "passage: ")
    Vt_query = codificar(MODELO_PADRAO, "temas_enri_v2_query", textos, "query: ")
    Vq = codificar(MODELO_PADRAO, "questoes100", q_textos, "query: ")
    assert Vq.shape[0] == n and Vt_pass.shape[0] == len(pool) and Vt_query.shape[0] == len(pool)

    M_emb_pass = (Vq @ Vt_pass.T).astype("float64")
    M_emb_query = (Vq @ Vt_query.T).astype("float64")
    Ms = {
        "rrf_all": M_lex,
        "emb_passage": M_emb_pass,
        "rrf_emb_passage": _rrf_de_matrizes(M_lex, M_emb_pass, k=RRF_K),
        "emb_query": M_emb_query,
        "rrf_emb_query": _rrf_de_matrizes(M_lex, M_emb_query, k=RRF_K),
    }

    validos = [q for q in ids if not bool(gold.loc[q, "fora"])]
    aceitos, alvos = {}, {}
    for q in validos:
        alvos[q] = set(gold.loc[q, "alvos"])
        aceitos[q] = {tema1(arv, t) for t in alvos[q] if tema1(arv, t)}

    linhas = []
    for k, qid in enumerate(ids):
        row = {
            "qid": qid,
            "valida": qid in aceitos,
            "disciplina": gold.loc[qid, "disciplina"],
            "assunto_origem": qmap.loc[qid, "assunto_origem"],
        }
        for nome, M in Ms.items():
            info = info_top1(M[k], pool, arv, aceitos.get(qid, set()), alvos.get(qid, set()))
            row[f"{nome}_top1"] = info["top1"]
            row[f"{nome}_branch"] = info["branch"]
            row[f"{nome}_rank"] = info["rank"]
            row[f"{nome}_correct"] = info["correct"] if qid in aceitos else None
            row[f"{nome}_exact"] = info["exact"] if qid in aceitos else None
        linhas.append(row)
    pq = pd.DataFrame(linhas)

    base_v = pq.loc[pq.valida, "rrf_all_correct"].astype(int).to_numpy()
    resumo = []
    for nome in ["rrf_all"] + VARIANTS:
        v = pq.loc[pq.valida, f"{nome}_correct"].astype(int).to_numpy()
        acertos = int(v.sum())
        lo_w, hi_w = wilson(acertos, len(v))
        if nome == "rrf_all":
            delta = dlo = dhi = 0.0
            ganhas = perdidas = 0
            p_mcnemar = None
        else:
            delta = float(v.mean() - base_v.mean())
            dlo, dhi = bootstrap_delta(v, base_v, b_=B)
            ganhas = int(((base_v == 0) & (v == 1)).sum())
            perdidas = int(((base_v == 1) & (v == 0)).sum())
            p_mcnemar = float(binomtest(min(ganhas, perdidas), ganhas + perdidas, 0.5).pvalue) \
                if (ganhas + perdidas) else 1.0
        rank5 = pq.loc[pq.valida, f"{nome}_rank"].fillna(10**9)
        rank10 = pq.loc[pq.valida, f"{nome}_rank"].fillna(10**9)
        exato = pq.loc[pq.valida, f"{nome}_exact"].astype(int).to_numpy()
        adotar = bool(nome != "rrf_all" and (acertos - int(base_v.sum())) >= 5 and dlo > 0)
        resumo.append({
            "variante": nome,
            "n": len(v),
            "acertos_ramo1": acertos,
            "ramo1": round(float(v.mean()), 4),
            "ramo1_lo": round(float(lo_w), 4),
            "ramo1_hi": round(float(hi_w), 4),
            "ramo5": round(float((rank5 <= 5).mean()), 4),
            "ramo10": round(float((rank10 <= 10).mean()), 4),
            "exato1": round(float(exato.mean()), 4),
            "ganho_questoes": acertos - int(base_v.sum()),
            "ganhas": ganhas,
            "perdidas": perdidas,
            "delta_pp": round(100 * delta, 2),
            "delta": round(delta, 4),
            "delta_lo": round(float(dlo), 4),
            "delta_hi": round(float(dhi), 4),
            "ic_pareado_acima_zero": bool(dlo > 0),
            "mcnemar_p": round(p_mcnemar, 6) if p_mcnemar is not None else None,
            "adotar": adotar,
        })
    res = pd.DataFrame(resumo)

    # Resumo por disciplina: descritivo, não decide adoção.
    disc = []
    for d in sorted(pq.loc[pq.valida, "disciplina"].unique()):
        qs = pq[(pq.valida) & (pq.disciplina == d)]
        row = {"disciplina": d, "n": len(qs)}
        for nome in ["rrf_all"] + VARIANTS:
            v = qs[f"{nome}_correct"].astype(int)
            row[f"{nome}_acertos"] = int(v.sum())
            row[f"{nome}_ramo1"] = round(float(v.mean()), 4)
        disc.append(row)
    pd.DataFrame(disc).to_csv(ARTEFATOS / "embeddings_v2_por_disciplina.csv", index=False)

    # CSV por questão: inclui as 8 fora (valida=False), para auditoria.
    pq.to_csv(ARTEFATOS / "embeddings_v2_por_questao.csv", index=False)
    res.to_csv(ARTEFATOS / "embeddings_v2_resumo.csv", index=False)

    meta = {
        "experimento": "embeddings_v2_temas_enriquecidos",
        "data": datetime.now().isoformat(timespec="seconds"),
        "modelo": MODELO_PADRAO,
        "n_questoes": n,
        "n_validas": len(validos),
        "n_temas": len(pool),
        "n_enriquecidos": len(enr),
        "criterio": {
            "ganho_minimo_questoes": 5,
            "ic_pareado": "bootstrap 95% das questoes, 2000 reamostragens, semente 42",
            "adotar": "ganho >= 5 e delta_lo > 0 contra rrf_all",
        },
        "prefixos": {"passage": "passage: ", "query": "query: "},
        "hash_textos_temas": _hash(textos),
        "hash_textos_questoes": hashlib.sha256(
            "\n".join(q_textos).encode("utf-8")).hexdigest()[:12],
        "matrizes": {k: list(v.shape) for k, v in Ms.items()},
        "rrf_k": RRF_K,
        "seed": SEED,
        "por_disciplina": disc,
        "resultado": res.to_dict(orient="records"),
    }
    (ARTEFATOS / "embeddings_v2_resumo.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== ramo@1 (92 válidas, regra do pai) ===")
    print(f"{'variante':18s} {'acertos':>7s} {'ramo1':>7s} {'delta':>7s} "
          f"{'IC 95%':>18s} {'g/p':>7s} {'adotar':>7s}")
    for r in res.itertuples():
        ic = f"[{r.delta_lo:+.4f}; {r.delta_hi:+.4f}]"
        gp = f"{r.ganhas}/{r.perdidas}" if r.variante != "rrf_all" else "—"
        print(f"{r.variante:18s} {r.acertos_ramo1:7d} {r.ramo1:7.3f} "
              f"{r.delta:+.3f} {ic:>18s} {gp:>7s} {str(r.adotar):>7s}")
    print("\nCSV:", ARTEFATOS / "embeddings_v2_resumo.csv")
    print("CSV:", ARTEFATOS / "embeddings_v2_por_questao.csv")


if __name__ == "__main__":
    main()
