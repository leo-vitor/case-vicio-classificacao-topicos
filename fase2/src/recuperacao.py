"""Nucleo de recuperacao de candidatos (offline, sem API).

Adaptado de `fase1/src/recuperacao.py` com duas mudancas deliberadas:

  1. `texto_tema` foi internalizado (a Fase 2 nao depende de `src.candidates`).
  2. Os vetorizadores sao ajustados APENAS no corpus de temas (371 textos), e nao
     no conjunto questao+tema. Isso torna o pipeline transdutivo de menos: a mesma
     configuracao pode ser usada em uma questao nova, sem refit.

Recuperadores disponiveis:
  tfidf            palavra 1-2, sublinear, sem acento
  tfidf_char       char_wb 3-5 (tolera ruido de digitacao e variacao morfologica)
  bm25             Okapi BM25 (k1=1.5, b=0.75)
  rrf_tfidf_bm25   Reciprocal Rank Fusion(tfidf, bm25)
  rrf_all          RRF(tfidf, char, bm25)

Metricas de recuperacao (regua do case: tema, pai ou filho direto; irmao NAO conta):
  recall_exato  o proprio tema_correto esta entre os k primeiros
  recall_hier   ha um candidato relacionado entre os k primeiros (teto do juiz)
"""
import math
import re
import unicodedata

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import MAX_FEATURES, RRF_K

RETRIEVERS = ["tfidf", "tfidf_char", "bm25", "rrf_tfidf_bm25", "rrf_all"]


def texto_tema(arv, tid):
    """Texto do tema: caminho + titulo (mesma definicao da Fase 1)."""
    return arv.caminho[tid].replace(">", " ") + " " + arv.titulo[tid]


def texto_questao(linha):
    """Enunciado + assunto_origem com peso 2 (pista de texto, nao verdade)."""
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

    def scores(self, query):
        q = _toks(query)
        sc = np.zeros(self.N)
        for i in range(self.N):
            tf, dl = self.f[i], len(self.docs[i])
            for t in q:
                if t in tf:
                    sc[i] += self.idf.get(t, 0.0) * (tf[t] * (self.k1 + 1)) / (
                        tf[t] + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                    )
        return sc


def _rrf_de_matrizes(*matrizes, k=RRF_K):
    """RRF a partir de matrizes de score (n_q, n_t): soma 1/(k+rank+1) de cada lista."""
    n_q, n_t = matrizes[0].shape
    out = np.zeros((n_q, n_t))
    for M in matrizes:
        for i in range(n_q):
            ordem = ordem_desc(M[i])
            for r, j in enumerate(ordem):
                out[i, j] += 1.0 / (k + r + 1)
    return out


class Busca:
    """Indice de temas. Ajustado uma vez, serve consultas de qualquer retriever."""

    def __init__(self, t_texts):
        self.t_texts = list(t_texts)
        self.vw = TfidfVectorizer(
            strip_accents="unicode", lowercase=True, ngram_range=(1, 2),
            sublinear_tf=True, min_df=1, max_features=MAX_FEATURES,
        )
        self.Mw = self.vw.fit_transform(self.t_texts)
        self.vc = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(3, 5), strip_accents="unicode",
            lowercase=True, sublinear_tf=True, min_df=1, max_features=MAX_FEATURES,
        )
        self.Mc = self.vc.fit_transform(self.t_texts)
        self._bm = None

    def bm25(self):
        if self._bm is None:
            self._bm = BM25(self.t_texts)
        return self._bm

    def scores(self, retriever, q_texts):
        """Matriz (n_q, n_t). Quanto maior, melhor. Escala varia por retriever."""
        if retriever == "tfidf":
            return cosine_similarity(self.vw.transform(q_texts), self.Mw)
        if retriever == "tfidf_char":
            return cosine_similarity(self.vc.transform(q_texts), self.Mc)
        if retriever == "bm25":
            return np.vstack([self.bm25().scores(q) for q in q_texts])
        Mw = cosine_similarity(self.vw.transform(q_texts), self.Mw)
        if retriever == "rrf_tfidf_bm25":
            Mb = np.vstack([self.bm25().scores(q) for q in q_texts])
            return _rrf_de_matrizes(Mw, Mb)
        if retriever == "rrf_all":
            Mc = cosine_similarity(self.vc.transform(q_texts), self.Mc)
            Mb = np.vstack([self.bm25().scores(q) for q in q_texts])
            return _rrf_de_matrizes(Mw, Mc, Mb)
        raise ValueError(f"retriever desconhecido: {retriever}")

    def ordem(self, retriever, q_texts):
        """Lista de arrays de indices ordenados (um por questao)."""
        M = self.scores(retriever, q_texts)
        return [ordem_desc(M[i]) for i in range(M.shape[0])], M


def ordem_desc(linha):
    """Indices do maior para o menor, com desempate estavel (menor indice vence).

    O desempate importa: os scores do RRF sao discretos e empatam com frequencia.
    Sem `kind="stable"`, `argsort` e `argmax` podem escolher maximos diferentes
    para a mesma linha, e o mesmo top-1 muda de dono entre modulos.
    """
    return np.argsort(-np.asarray(linha), kind="stable")


def sinais(M, i):
    """Sinais de confianca do topo do ranking para a questao i.

    abs : score bruto do top-1 (comparavel dentro do mesmo retriever)
    rel : s1/(s1+s2)  -> livre de escala (0,5 = empate; 1 = vencedor claro)
    gap : (s1-s2)/s1  -> livre de escala
    """
    linha = M[i]
    ordem = ordem_desc(linha)[:2]
    s1 = float(linha[ordem[0]])
    s2 = float(linha[ordem[1]]) if len(ordem) > 1 else 0.0
    return {
        "idx_top1": int(ordem[0]),
        "s1": s1,
        "s2": s2,
        "abs": s1,
        "rel": s1 / (s1 + s2) if (s1 + s2) > 0 else 0.5,
        "gap": (s1 - s2) / s1 if s1 > 0 else 0.0,
    }
