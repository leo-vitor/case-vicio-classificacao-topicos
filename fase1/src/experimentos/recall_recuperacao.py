"""Experimento (offline, custo zero de API): recall da etapa de recuperacao de candidatos.

Motivacao: o diagnostico dos 11 erros mostrou que o gargalo dominante e a RECUPERACAO
(o tema certo nao estava entre os candidatos oferecidos ao juiz), nao a decisao.
Aqui medimos, contra os 93 rotulos, se o tema correto (ou o seu pai/filho) entra no
conjunto de candidatos sob diferentes recuperadores e expansoes.

Nao altera nada do pipeline: so le e grava em outputs/experimentos/.

  python -m src.experimentos.recall_recuperacao

O que "recall" significa aqui, sob a regua do case (mesmo no / pai / filho):
  - recall_exato : o proprio tema_correto_id esta entre os candidatos.
  - recall_1hop  : existe candidato relacionado (tema, pai ou filho). E o que basta
                   para o juiz poder acertar. Irmaos NAO contam.
  - recall_via_pai : o pai do tema correto esta na lista (sem contar o exato).

Conjuntos de candidatos comparados:
  top          : apenas os K mais similares.
  +pai         : top + pais dos candidatos.
  +filho       : top + pais + filhos dos 3 primeiros (logica atual de candidates.py).
  +irmao       : +filho + irmaos dos candidatos (o que a proposta "expansao" acrescenta).

Recuperadores comparados:
  tfidf : configuracao atual (candidates.py).
  bm25  : Okapi BM25 lexico.
  rrf   : fusao de postos (Reciprocal Rank Fusion, k=60) de tfidf + bm25.
"""
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import CACHE, OUT, TOP_K
from src.temas import Arvore

EXP = OUT / "experimentos"
EXP.mkdir(exist_ok=True)
KS = [5, 10, 15, 20, 30]
RRF_K = 60
DENSE_MODEL = os.getenv("DENSE_MODEL", "intfloat/multilingual-e5-small")


def _embed_denso(m, texts, rotulo):
    """Embeddings densos locais (sem API), com cache em disco. Modelo e5 pede prefixos."""
    from sentence_transformers import SentenceTransformer

    pref = "query: " if rotulo == "q" else "passage: "
    if "e5" in m:
        texts = [pref + t for t in texts]
    key = hashlib.sha256((m + "||" + rotulo + "||" + "||".join(texts)).encode()).hexdigest()[:24]
    f = CACHE / f"emb_denso_{key}.npy"
    if f.exists():
        return np.load(f)
    model = SentenceTransformer(m)
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    arr = np.array(vecs, dtype="float32")
    np.save(f, arr)
    return arr


def _rank_denso(m, q_texts, t_texts):
    q = _embed_denso(m, q_texts, "q")
    t = _embed_denso(m, t_texts, "t")
    sim = q @ t.T
    return [np.argsort(-sim[i]) for i in range(sim.shape[0])]


# ---------------------------------------------------------------- tokenizacao
def toks(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", s.lower())


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [toks(d) for d in docs]
        self.k1, self.b = k1, b
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(self.N, 1)
        self.f, df = [], {}
        for d in self.docs:
            tf = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            self.f.append(tf)
            for t in tf:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def score(self, query, i):
        q = toks(query)
        tf, dl = self.f[i], len(self.docs[i])
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            s += self.idf.get(t, 0.0) * (tf[t] * (self.k1 + 1)) / (
                tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
        return s

    def ranking(self, query):
        sc = np.array([self.score(query, i) for i in range(self.N)])
        return np.argsort(-sc)


def ranking_tfidf(q_texts, t_texts):
    vec = TfidfVectorizer(
        strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True, min_df=1
    )
    vec.fit(q_texts + t_texts)
    M = cosine_similarity(vec.transform(q_texts), vec.transform(t_texts))
    return M, [np.argsort(-M[i]) for i in range(M.shape[0])]


def ranking_bm25(q_texts, t_texts):
    bm = BM25(t_texts)
    return [bm.ranking(qt) for qt in q_texts]


def rrf_rank(a, b, k=RRF_K):
    """Reciprocal Rank Fusion de duas ordenacoes; devolve a ordenacao fundida."""
    sc = {}
    for ordem in (a, b):
        for r, idx in enumerate(ordem):
            sc[int(idx)] = sc.get(int(idx), 0.0) + 1.0 / (k + r + 1)
    return np.array(sorted(sc, key=lambda x: -sc[x]))


def rrf_rank3(a, b, c, k=RRF_K):
    sc = {}
    for ordem in (a, b, c):
        for r, idx in enumerate(ordem):
            sc[int(idx)] = sc.get(int(idx), 0.0) + 1.0 / (k + r + 1)
    return np.array(sorted(sc, key=lambda x: -sc[x]))


# ---------------------------------------------------------------- expansao
def expandir(arv, top, mode):
    C = list(top)
    if mode == "top":
        return C

    def add(x):
        if x and arv.publicavel(x) and x not in C:
            C.append(x)

    if mode in ("+pai", "+filho", "+irmao", "+irmao3"):
        for t in top:
            add(arv.parent.get(t))
    if mode in ("+filho", "+irmao", "+irmao3"):
        for t in top[:3]:
            if arv.nivel.get(t) == 1:
                for c in arv.filhos.get(t, []):
                    add(c)
    if mode == "+irmao":
        for t in top:
            p = arv.parent.get(t)
            for s in arv.filhos.get(p, []):
                add(s)
    if mode == "+irmao3":
        for t in top[:3]:
            p = arv.parent.get(t)
            for s in arv.filhos.get(p, []):
                add(s)
    return C


# ---------------------------------------------------------------- metricas
def recall(arv, ids, cands_by_id, rot):
    n = len(ids)
    exato = hop = pai = 0
    for i in ids:
        C = cands_by_id[i]
        t = rot[i]
        if t in C:
            exato += 1
        if any(arv.relacionado(t, c) for c in C):
            hop += 1
        elif arv.parent.get(t) in C:
            pai += 1
    return n, exato, hop, pai


def main():
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")
    rot = pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")
    rot = rot[rot["tema_correto_id"] != ""]
    rotmap = dict(zip(rot.id, rot.tema_correto_id))
    ids = [i for i in q.id if i in rotmap]
    q = q.set_index("id")

    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    t_texts = [(arv.caminho[t].replace(">", " ") + " " + arv.titulo[t]) for t in pool]
    # texto da questao igual ao candidates.py: enunciado + assunto_origem (peso 2)
    q_texts = [
        (q.loc[i, "texto"] + " " + q.loc[i, "assunto_origem"] + " " + q.loc[i, "assunto_origem"])
        for i in ids
    ]

    print(f"Rotuladas com tema: {len(ids)} | temas publicaveis: {len(pool)}")

    M, r_tfidf = ranking_tfidf(q_texts, t_texts)
    r_bm25 = ranking_bm25(q_texts, t_texts)
    r_rrf = [rrf_rank(r_tfidf[i], r_bm25[i]) for i in range(len(ids))]
    rankings = {"tfidf": r_tfidf, "bm25": r_bm25, "rrf": r_rrf}
    try:
        r_denso = _rank_denso(DENSE_MODEL, q_texts, t_texts)
        rankings["denso"] = r_denso
        rankings["rrf_d"] = [rrf_rank(r_tfidf[i], r_denso[i]) for i in range(len(ids))]
        rankings["rrf3"] = [rrf_rank3(r_tfidf[i], r_bm25[i], r_denso[i]) for i in range(len(ids))]
        print(f"Embedder denso ativo: {DENSE_MODEL}")
    except Exception as e:  # noqa: BLE001
        print(f"[aviso] denso indisponivel ({type(e).__name__}): {e}")

    MODES = ["top", "+pai", "+filho", "+irmao3", "+irmao"]
    linhas = []
    for ranker, rk in rankings.items():
        for mode in MODES:
            for k in KS:
                cands = {}
                for i, qid in enumerate(ids):
                    top = [pool[j] for j in rk[i][:k]]
                    cands[qid] = expandir(arv, top, mode)
                n, ex, hop, pai = recall(arv, ids, cands, rotmap)
                tam = float(np.mean([len(v) for v in cands.values()]))
                linhas.append(
                    {"ranker": ranker, "mode": mode, "k": k, "n": n,
                     "recall_exato": ex / n, "recall_1hop": hop / n,
                     "recall_via_pai": pai / n, "cands_media": round(tam, 1)}
                )
    df = pd.DataFrame(linhas)
    df.to_csv(EXP / "recall_recuperacao.csv", index=False)

    # ---- tabela principal: k=10, todos rankers x modes
    print("\n=== k=10 (recall e tamanho medio da lista de candidatos) ===")
    d10 = df[df.k == 10].set_index(["ranker", "mode"])[
        ["recall_exato", "recall_1hop", "cands_media"]
    ]
    print(d10.round(3).to_string())

    # ---- sweep de k para as expansoes que importam
    print("\n=== recall_1hop por k (permite o juiz acertar) ===")
    for ranker in rankings:
        for mode in ["+filho", "+irmao3", "+irmao"]:
            sub = df[(df.ranker == ranker) & (df["mode"] == mode)].set_index("k")["recall_1hop"]
            print(f"  {ranker:6s} {mode:7s}: " + "  ".join(f"k={k}:{sub[k]:.2f}" for k in KS))

    # ---- recall do candidatos.json de fato (pos-fallback) ----
    cj = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    cands_real = {i: cj[i]["candidatos"] for i in ids}
    n, ex, hop, pai = recall(arv, ids, cands_real, rotmap)
    print(
        f"\n=== candidatos.json ATUAL (pos-fallback): exato {ex}/{n}={ex/n:.3f} | "
        f"1hop {hop}/{n}={hop/n:.3f} | via_pai {pai}/{n}={pai/n:.3f} ==="
    )
    print("  (cuidado: parte das questoes teve a arvore inteira no fallback; recall nao e comparavel 1:1)")

    # ---- melhor config (ranker x modo) em recall_1hop @ k=10 ----
    top10 = df[df.k == 10].sort_values("recall_1hop", ascending=False)
    br, bm = top10.iloc[0]["ranker"], top10.iloc[0]["mode"]
    print(f"\n=== melhor config gratuita: {br} {bm} (k=10, recall_1hop {top10.iloc[0]['recall_1hop']:.3f}) ===")
    cands = {}
    for i, qid in enumerate(ids):
        top = [pool[j] for j in rankings[br][i][:10]]
        cands[qid] = expandir(arv, top, bm)
    print(f"\n=== por disciplina ({br} {bm}, k=10) ===")
    disc = {}
    for i in ids:
        d = arv.raiz(rotmap[i])
        C = cands[i]
        t = rotmap[i]
        ok = any(arv.relacionado(t, c) for c in C)
        disc.setdefault(d, [0, 0])
        disc[d][0] += 1
        disc[d][1] += int(ok)
    for d, (tot, ok) in sorted(disc.items(), key=lambda x: -x[1][0]):
        print(f"  {d:42s} {ok}/{tot} = {ok/tot:.2f}")

    # ---- falhas de recuperacao (1hop) na melhor config ----
    faltas = [i for i in ids if not any(arv.relacionado(rotmap[i], c) for c in cands[i])]
    print(f"\n=== {len(faltas)} questoes em que nem o tema nem o pai entram ({br} {bm}, k=10) ===")
    print("  " + ", ".join(faltas))
    pd.DataFrame({"id": faltas}).to_csv(EXP / "recall_faltas.csv", index=False)


if __name__ == "__main__":
    main()
