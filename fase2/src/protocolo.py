"""Protocolo de avaliacao da Fase 2 (Etapa 0).

Aqui ficam as definicoes que TODO metodo tem de respeitar, para que os numeros
sejam comparaveis e honestos:

  - regua de acerto do case (tema central, extra, pai ou filho direto);
  - validacao cruzada repetida e estratificada, com near-duplicatas no mesmo fold;
  - intervalo de confianca de Wilson para proporcoes;
  - escolha do limiar FORA da dobra (nested), que e o unico ponto "aprendido" da
    regra v0. Sem isso, a precisao reportada fica otimista.

A folha-verdade (100 questoes) e a unica base rotulada. As 559 restantes nao tem
rotulo de especialista e entram apenas na previsao, nunca no treino.
"""
from itertools import count

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import (
    ALVO_PRECISAO,
    ARTEFATOS,
    DATA,
    LIMIAR_DUPLICATA,
    N_SPLITS,
    SEED,
    Z_CONFIANCA,
)
from src.temas import Arvore


# ---------------------------------------------------------------- dados

def carregar_questoes():
    p = ARTEFATOS / "questoes_limpas.csv"
    if not p.exists():
        from src.clean import quadro

        return quadro()
    return pd.read_csv(p, dtype=str).fillna("")


def carregar_gold(arv):
    """Le a folha-verdade e devolve um DataFrame indexavel por id.

    Colunas: tema, extras (lista), fora (bool), alvos (lista), disciplina, faixa.
    """
    df = pd.read_csv(DATA / "folha_verdade.csv", dtype=str).fillna("")
    df["extras"] = df["extras_ids"].map(lambda s: [x for x in s.split(";") if x])
    df["fora"] = df["fora_da_taxonomia"].astype(int).astype(bool)
    df["alvos"] = [
        ([r.tema_central_id] if r.tema_central_id else []) + r.extras
        for r in df.itertuples()
    ]
    df["disciplina"] = df["tema_central_id"].map(
        lambda t: arv.raiz(t) if t else "fora_da_taxonomia"
    )
    df["faixa"] = df["id"].str[1:].astype(int).map(
        lambda n: "antiga" if n <= 359 else "nova"
    )
    return df.set_index("id", drop=False)


def acerto(arv, alvos_lista, pred):
    """Regua do case aplicada a um unico id. pred vazio (revisar/fora) nunca e 'publicado'."""
    if not pred or not alvos_lista:
        return False
    return any(arv.relacionado(pred, t) for t in alvos_lista)


def estratos(gold):
    """Estrato = disciplina do tema central (ou 'fora_da_taxonomia')."""
    return list(gold["disciplina"])


# ---------------------------------------------------------------- folds

def grupos_duplicados(textos, limiar=LIMIAR_DUPLICATA):
    """Union-find sobre similaridade de cosseno. Devolve o id do grupo por posicao."""
    if len(textos) <= 1:
        return list(range(len(textos)))
    vec = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True)
    M = vec.fit_transform(textos)
    S = cosine_similarity(M)
    pai = list(range(len(textos)))

    def raiz(a):
        while pai[a] != a:
            pai[a] = pai[pai[a]]
            a = pai[a]
        return a

    for i in range(len(textos)):
        for j in range(i + 1, len(textos)):
            if S[i, j] >= limiar:
                ri, rj = raiz(i), raiz(j)
                if ri != rj:
                    pai[ri] = rj
    rot = {}
    saida = []
    for i in range(len(textos)):
        r = raiz(i)
        if r not in rot:
            rot[r] = len(rot)
        saida.append(rot[r])
    return saida


def folds_estratificados(estratos_, grupos, n_splits=N_SPLITS, seed=SEED):
    """Folds estratificados que nunca separam near-duplicatas.

    Passos: agrupa duplicatas -> cada grupo recebe o estrato dominante -> embaralha
    dentro do estrato -> distribui nos folds equilibrando o tamanho. Determinismo
    via seed, para que todos os metodos usem exatamente os mesmos folds.
    """
    n = len(estratos_)
    grp_membros = {}
    for i, g in enumerate(grupos):
        grp_membros.setdefault(g, []).append(i)
    grp_estrato = {}
    for g, membros in grp_membros.items():
        cont = pd.Series([estratos_[i] for i in membros]).value_counts()
        grp_estrato[g] = cont.index[0]

    rng = np.random.default_rng(seed)
    por_estrato = {}
    for g, e in grp_estrato.items():
        por_estrato.setdefault(e, []).append(g)

    grupos_por_fold = [[] for _ in range(n_splits)]
    for e, gs in por_estrato.items():
        gs = list(gs)
        rng.shuffle(gs)
        for g in gs:
            tamanhos = [sum(len(grp_membros[x]) for x in f) for f in grupos_por_fold]
            alvo = int(np.argmin(tamanhos))
            grupos_por_fold[alvo].append(g)

    folds = []
    for k in range(n_splits):
        teste = sorted(i for g in grupos_por_fold[k] for i in grp_membros[g])
        treino = [i for i in range(n) if i not in set(teste)]
        folds.append((np.array(treino), np.array(teste)))
    return folds


# ---------------------------------------------------------------- metricas

def wilson(k, n, z=Z_CONFIANCA):
    """Intervalo de confianca de Wilson para uma proporcao (k sucessos em n)."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - meia), min(1.0, centro + meia)


def beta_binomial(acertos, publicadas, a0=1.0, b0=1.0):
    """Posterior Beta-Binomial da precisao (intervalo credivel de 95%).

    Substitui a formula artesanal de previsao: com 20 publicadas e 19 acertos, o
    intervalo tem de vir da distribuicao, nao de um desconto escolhido a mao.
    Prior Beta(1,1) = uniforme, ou seja, o numero sai dos dados.
    """
    from scipy.stats import beta as _beta

    a, b = a0 + acertos, b0 + (publicadas - acertos)
    lo, hi = _beta.ppf([0.025, 0.975], a, b)
    return {"acertos": int(acertos), "publicadas": int(publicadas),
            "media": float(a / (a + b)), "lo": float(lo), "hi": float(hi)}


def curva(scores, corretos, n_grade=200):
    """Curva precisao x cobertura variando o limiar. Nao aprende nada: so descreve."""
    scores = np.asarray(scores, dtype=float)
    corretos = np.asarray(corretos, dtype=bool)
    n = len(scores)
    limiares = np.unique(np.quantile(scores, np.linspace(0, 1, n_grade)))
    linhas = []
    for t in sorted(limiares, reverse=True):
        pub = scores >= t
        m = int(pub.sum())
        ac = int((pub & corretos).sum())
        prec = ac / m if m else float("nan")
        lo, hi = wilson(ac, m)
        linhas.append(
            {
                "limiar": float(t),
                "publicados": m,
                "acertos": ac,
                "precisao": prec,
                "precisao_lo": lo,
                "precisao_hi": hi,
                "cobertura": m / n,
            }
        )
    return pd.DataFrame(linhas)


def ponto_oof(scores, corretos, folds, alvo=ALVO_PRECISAO, criterio="wilson"):
    """Escolhe o limiar no treino de cada fold e mede no teste (pooled).

    criterio='wilson'  exige limite INFERIOR da precisao no treino >= alvo
    criterio='ponto'   exige a precisao pontual no treino >= alvo

    Devolve as predicoes fora da dobra e o resumo.
    """
    scores = np.asarray(scores, dtype=float)
    corretos = np.asarray(corretos, dtype=bool)
    n = len(scores)
    pred = np.zeros(n, dtype=bool)
    limiares, dobras = [], []
    for tr, te in folds:
        melhor, melhor_cob = np.inf, -1.0
        for t in np.unique(scores[tr]):
            pub = scores[tr] >= t
            m = int(pub.sum())
            if m == 0:
                continue
            ac = int((pub & corretos[tr]).sum())
            ok = (wilson(ac, m)[0] >= alvo) if criterio == "wilson" else (ac / m >= alvo)
            if ok and m > melhor_cob:
                melhor_cob, melhor = m, float(t)
        t_fold = melhor if melhor != np.inf else float(np.inf)
        limiares.append(t_fold)
        pub_te = scores[te] >= t_fold
        pred[te] = pub_te
        m = int(pub_te.sum())
        ac = int((pub_te & corretos[te]).sum())
        dobras.append(
            {"teste_n": len(te), "limiar": t_fold, "publicados": m, "acertos": ac,
             "precisao": ac / m if m else float("nan")}
        )
    m = int(pred.sum())
    ac = int((pred & corretos).sum())
    lo, hi = wilson(ac, m)
    return {
        "criterio": criterio,
        "alvo": alvo,
        "publicados": m,
        "acertos": ac,
        "precisao": ac / m if m else float("nan"),
        "precisao_lo": lo,
        "precisao_hi": hi,
        "cobertura": m / n,
        "limiares_por_fold": limiares,
        "por_fold": dobras,
        "pred": pred,
    }
