"""Conformal / decisao seletiva com garantia (Fase 2).

Tres ferramentas, todas na mesma base: as 100 questoes rotuladas e a probabilidade
fora da dobra `p_oof` (de um modelo que nao viu a questao).

1. CRC (conformal risk control) sobre a perda conjunta
   perda_i = 1 se publicada e errada, 0 caso contrario.
   Garantia: E[P(publicar e errar)] <= alpha.  NAO e o mesmo que
   P(errar | publicada) <= alpha: e mais fraco. Serve para dizer quantas
   publicacoes erradas, no total, a amostra sustenta.

2. Precisao CERTIFICAVEL
   Maior cobertura cuja cota superior exata (Clopper-Pearson) do erro entre as
   publicadas fica <= alpha. E o instrumento honesto para responder
   "95% se sustenta com 100 rotulos?" — quase sempre a resposta e nao.

3. Conjuntos conformais por RANKING + regra do ancestral comum
   Conjunto = os k_hat melhores temas, com k_hat calibrado para que o gabarito
   esteja dentro do conjunto em (1-alpha) dos casos. Regra: se o conjunto inteiro
   cai dentro de um unico ramo (um tema de nivel 1 e seus filhos), publica-se esse
   tema. Como a regua aceita o pai, o acerto segue a cobertura do conjunto.

Uso (da pasta fase2/):
    python -m src.conformal
"""
import json

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

from src.recuperacao import ordem_desc

from src.artefato import base, tema1
from src.config import ARTEFATOS
from src.protocolo import acerto


# ------------------------------------------------------------------ cotas

def clopper_upper(e, m, alpha):
    """Cota superior exata (Clopper-Pearson) do erro, com confianca 1-alpha."""
    if m == 0:
        return 1.0
    if e >= m:
        return 1.0
    return float(beta_dist.ppf(1 - alpha, e + 1, m - e))


def crc(base_mask, scores, errados, alpha):
    """Limiar por conformal risk control (Angelopoulos et al.).

    lambda_hat = inf{ lambda : (n/(n+1)) * Rhat(lambda) + 1/(n+1) <= alpha },
    com Rhat = perda conjunta media. A perda e nao-crescente em lambda, entao
    o primeiro lambda (em ordem crescente) que satisfaz da a maior cobertura.
    """
    n = len(scores)
    for lam in np.unique(scores):
        pub = base_mask & (scores >= lam)
        R = float(np.mean(pub & errados))
        if (n / (n + 1)) * R + 1 / (n + 1) <= alpha:
            return float(lam), pub
    return None, np.zeros(n, dtype=bool)


def certificado(base_mask, scores, errados, alpha):
    """Maior cobertura cuja precisao pode ser CERTIFICADA a (1-alpha)."""
    for lam in np.unique(scores):
        pub = base_mask & (scores >= lam)
        m = int(pub.sum())
        if m == 0:
            continue
        e = int((pub & errados).sum())
        if clopper_upper(e, m, alpha) <= alpha:
            return float(lam), pub
    return None, np.zeros(len(scores), dtype=bool)


# ------------------------------------------------------- conjuntos conformais

def ranks_do_gabarito(arv, pool, M, ids, gold):
    """Posicao (1-based) do gabarito no ranking de temas. Fora da taxonomia -> nan."""
    pos = {t: j for j, t in enumerate(pool)}
    r = []
    for i, qid in enumerate(ids):
        alvos = [t for t in gold.loc[qid, "alvos"] if t in pos]
        if not alvos:
            r.append(np.nan)
            continue
        ordem = ordem_desc(M[i])
        posto = {pool[j]: k + 1 for k, j in enumerate(ordem)}
        r.append(min(posto[t] for t in alvos))
    return np.array(r, dtype=float)


def k_conformal(ranks, alpha):
    """k_hat = ordem (n+1)(1-alpha) das posicoes do gabarito."""
    r = ranks[~np.isnan(ranks)]
    n = len(r)
    if n == 0:
        return 1
    k = int(np.ceil((n + 1) * (1 - alpha)))
    k = min(k, n)
    return int(np.sort(r)[k - 1])


def avaliar_confinamento(arv, pool, M, ids, gold, k):
    """Publica o tema de nivel 1 do top-k quando o top-k inteiro cai num so ramo."""
    pub, ac = 0, 0
    for i, qid in enumerate(ids):
        ordem = ordem_desc(M[i])[:k]
        ramos = {tema1(arv, pool[j]) for j in ordem}
        ramos.discard(None)
        if len(ramos) != 1:
            continue
        v = ramos.pop()
        pub += 1
        if acerto(arv, gold.loc[qid, "alvos"], v):
            ac += 1
    return pub, ac


def main():
    b = base()
    arv, gold, ids = b["arv"], b["gold"], b["ids"]
    pool, M = b["pool"], b["M"]
    y = b["y"]
    errados = 1 - y
    cons = b["cons"]
    p_oof = b["p_oof"]
    folds = b["folds"]
    base1 = cons >= 1.0

    out = {}

    # ---- 1. CRC por nivel de risco -------------------------------------
    crc_tab = []
    for alpha in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        lam, pub = crc(base1, p_oof, errados, alpha)
        m = int(pub.sum())
        ac = int(y[pub].sum())
        crc_tab.append({
            "alpha": alpha, "limiar": None if lam is None else round(lam, 4),
            "publicados": m, "acertos": ac,
            "precisao": round(ac / m, 4) if m else None,
            "cobertura": round(m / len(y), 4),
        })
    out["crc"] = crc_tab

    # ---- 2. fronteira de precisao certificavel -------------------------
    cert_tab = []
    for alpha in (0.05, 0.08, 0.10, 0.12, 0.14, 0.15, 0.16, 0.18, 0.20, 0.25):
        lam, pub = certificado(base1, p_oof, errados, alpha)
        m = int(pub.sum())
        ac = int(y[pub].sum())
        cert_tab.append({
            "alpha_erro": alpha, "limiar": None if lam is None else round(lam, 4),
            "publicados": m, "acertos": ac,
            "precisao_observada": round(ac / m, 4) if m else None,
            "cota_superior_erro": round(clopper_upper(m - ac, m, alpha), 4) if m else None,
            "cobertura": round(m / len(y), 4),
        })
    out["certificado"] = cert_tab

    # ---- 3. conjuntos conformais ---------------------------------------
    ranks = ranks_do_gabarito(arv, pool, M, ids, gold)
    conf_tab = []
    for alpha in (0.05, 0.10, 0.20):
        k = k_conformal(ranks, alpha)
        validos = ~np.isnan(ranks)
        cob_conj = float(np.mean(ranks[validos] <= k))
        # regra do ancestral comum, calibrando k FORA do grupo medido
        pub = ac = 0
        for tr, te in folds[:5]:
            tr_set = set(int(i) for i in tr)
            k_tr = k_conformal(ranks[sorted(tr_set)], alpha)
            for i in te:
                i = int(i)
                ordem = ordem_desc(M[i])[:k_tr]
                ramos = {tema1(arv, pool[j]) for j in ordem}
                ramos.discard(None)
                if len(ramos) != 1:
                    continue
                pub += 1
                if acerto(arv, gold.loc[ids[i], "alvos"], ramos.pop()):
                    ac += 1
        conf_tab.append({
            "alpha": alpha, "k_hat": k, "cobertura_conjunto": round(cob_conj, 4),
            "publicados": pub, "acertos": ac,
            "precisao": round(ac / pub, 4) if pub else None,
            "cobertura_regra": round(pub / len(y), 4),
        })
    out["conjuntos_conformais"] = conf_tab

    # curva descritiva de confinamento (k de 1 a 20, sem garantia)
    curva = []
    for k in range(1, 21):
        pub, ac = avaliar_confinamento(arv, pool, M, ids, gold, k)
        curva.append({"k": k, "publicados": pub,
                      "precisao": round(ac / pub, 4) if pub else None,
                      "cobertura": round(pub / len(y), 4)})
    out["curva_confinamento"] = curva

    (ARTEFATOS / "conformal.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 1. CRC (perda conjunta: publicar e errar) ===")
    print(pd.DataFrame(crc_tab).to_string(index=False))
    print("\n=== 2. precisao CERTIFICAVEL (Clopper-Pearson) ===")
    print(pd.DataFrame(cert_tab).to_string(index=False))
    print("\n=== 3. conjuntos conformais + ancestral comum ===")
    print(pd.DataFrame(conf_tab).to_string(index=False))
    print("\n=== curva de confinamento do top-k (descritiva) ===")
    print(pd.DataFrame(curva).to_string(index=False))


if __name__ == "__main__":
    main()
