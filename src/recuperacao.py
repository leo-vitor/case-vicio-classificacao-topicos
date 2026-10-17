"""Nucleo de recuperacao de candidatos (offline, sem API).

Fonte unica da verdade para os experimentos de recuperacao: retrievers, expansoes de
candidatos e o dicionario. É usado por `src.eval` (avaliacao canonica) e mantem a
mesma logica de `src/candidates.py` (texto do tema = caminho + titulo; texto da questao
= enunciado + assunto_origem com peso 2).

Metricas de recuperacao (regua do case: tema, pai ou filho direto; irmao NAO conta):
  - recall_exato : o proprio tema_correto_id esta na lista de candidatos.
  - recall_hier  : existe candidato relacionado (tema, pai ou filho direto). E o que
                   basta para o juiz poder acertar.
  - recall_via_pai: conta so os casos em que o pai entra, mas o exato nao.

Denominador em todas: n = numero de questoes rotuladas avaliadas (explicito no relatorio).
"""
import math
import re
import unicodedata

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.candidates import texto_tema
from src.config import CACHE

# Expansoes de CANDIDATOS (crescem a lista oferecida ao juiz)
MODOS = ["top", "pai", "filho", "irmao3", "irmao"]
# Recuperadores
RETRIEVERS = ["tfidf", "bm25", "rrf"]
RRF_K = 60


def pool_publicavel(arv):
    return [t for t in arv.ativos.tema_id if arv.publicavel(t)]


def textos_temas(arv, pool):
    return [texto_tema(arv, t) for t in pool]


def texto_questao(linha):
    """Igual a src/candidates.py: enunciado + assunto_origem repetido (peso 2)."""
    return (linha["texto"] + " " + linha["assunto_origem"] + " " + linha["assunto_origem"]).strip()


def _toks(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", s.lower())


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [_toks(d) for d in docs]
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

    def ranking(self, query):
        q = _toks(query)
        sc = np.zeros(self.N)
        for i in range(self.N):
            tf, dl = self.f[i], len(self.docs[i])
            for t in q:
                if t in tf:
                    sc[i] += self.idf.get(t, 0.0) * (tf[t] * (self.k1 + 1)) / (
                        tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    )
        return np.argsort(-sc)


def rank_tfidf(q_texts, t_texts):
    vec = TfidfVectorizer(
        strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True, min_df=1
    )
    vec.fit(q_texts + t_texts)
    M = cosine_similarity(vec.transform(q_texts), vec.transform(t_texts))
    return M, [np.argsort(-M[i]) for i in range(M.shape[0])]


def rank_bm25(q_texts, t_texts):
    bm = BM25(t_texts)
    return [bm.ranking(qt) for qt in q_texts]


def _rrf(ordens, k=RRF_K):
    sc = {}
    for ordem in ordens:
        for r, idx in enumerate(ordem):
            sc[int(idx)] = sc.get(int(idx), 0.0) + 1.0 / (k + r + 1)
    return np.array(sorted(sc, key=lambda x: -sc[x]))


def ranking(retriever, q_texts, t_texts):
    """Devolve lista de rankings (um por questao) e, para tfidf, a matriz de similaridade."""
    if retriever == "tfidf":
        M, r = rank_tfidf(q_texts, t_texts)
        return r, M
    if retriever == "bm25":
        return rank_bm25(q_texts, t_texts), None
    if retriever == "rrf":
        M, r_tf = rank_tfidf(q_texts, t_texts)
        r_bm = rank_bm25(q_texts, t_texts)
        return [_rrf([r_tf[i], r_bm[i]]) for i in range(len(q_texts))], M
    raise ValueError(f"retriever desconhecido: {retriever}")


def expandir(arv, top, modo):
    """Expansao de CANDIDATOS. 'top' = so o topk; os demais acrescentam vizinhos publicaveis."""
    C = list(top)
    if modo == "top":
        return C

    def add(x):
        if x and arv.publicavel(x) and x not in C:
            C.append(x)

    if modo in ("pai", "filho", "irmao", "irmao3"):
        for t in top:
            add(arv.parent.get(t))
    if modo in ("filho", "irmao"):
        for t in top[:3]:
            if arv.nivel.get(t) == 1:
                for c in arv.filhos.get(t, []):
                    add(c)
    if modo == "irmao":
        for t in top:
            for s in arv.filhos.get(arv.parent.get(t), []):
                add(s)
    if modo == "irmao3":
        for t in top[:3]:
            for s in arv.filhos.get(arv.parent.get(t), []):
                add(s)
    return C


def montar_candidatos(arv, pool, rank_i, k, modo):
    top = [pool[j] for j in rank_i[:k]]
    return expandir(arv, top, modo)


def avaliar(arv, ids, cands_por_id, rot):
    """Metricas explicitas. 'ids' e o denominador (n). Devolve tambem os erros e o por-disciplina."""
    n = len(ids)
    exato = hier = via_pai = 0
    erros, por_disc = [], {}
    for i in ids:
        C, t = cands_por_id[i], rot[i]
        ok_exato = t in C
        ok_hier = any(arv.relacionado(t, c) for c in C)
        exato += int(ok_exato)
        hier += int(ok_hier)
        if (not ok_exato) and arv.parent.get(t) in C:
            via_pai += 1  # o tema so entrou porque o pai foi recuperado
        if not ok_hier:
            erros.append(i)
        d = arv.raiz(t)
        por_disc.setdefault(d, [0, 0])
        por_disc[d][0] += 1
        por_disc[d][1] += int(ok_hier)
    return {
        "n": n,
        "recall_exato": exato / n if n else 0.0,
        "recall_hier": hier / n if n else 0.0,
        "recall_via_pai": via_pai / n if n else 0.0,
        "cands_media": float(np.mean([len(cands_por_id[i]) for i in ids])) if n else 0.0,
        "erros": erros,
        "por_disciplina": {d: {"n": tot, "acertos": ok, "recall": ok / tot} for d, (tot, ok) in por_disc.items()},
    }
