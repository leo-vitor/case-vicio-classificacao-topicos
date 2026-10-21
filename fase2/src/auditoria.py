"""Auditoria da decisao seletiva (Fase 2) — os 6 itens pedidos.

Este modulo NAO mexe na arquitetura (recuperacao, features, regra do pai). Ele
audita apenas a CAMADA DE DECISAO e a PREVISAO:

  1. Protocolo aninhado: as probabilidades usadas para escolher o limiar no treino
     vinham dos mesmos 25 folds — ou seja, de modelos que podiam ter visto o grupo
     de teste externo. Aqui isso e corrigido (`nested_corrigido`) e comparado.
  2. Sensibilidade da metrica hierarquica: leitura literal (regua do case),
     estrita (so o tema exato / extras) e frouxa (mesmo ramo de nivel 1).
  3. Regras manuais x logistica x logistica com bagging, nos MESMOS folds e com o
     limiar escolhido no treino. Se empatarem dentro do ruido, vale a manual.
  4. Beta-Binomial para a precisao prevista, substituindo a formula artesanal.
  5. Ponto de operacao: origem das publicacoes e a incompatibilidade de escala
     entre tau (modelos de 80) e p_all (modelo dos 100).
  6. Manifesto de proveniencia (versao, hashes, sementes, parametros).

Uso (da pasta fase2/):
    python -m src.auditoria
"""
import hashlib
import json
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

from src.artefato import base, tema1
from src.conformal import certificado
from src.config import ALVO_PRECISAO, ARTEFATOS, ROOT, SEED
from src.decisao import escolher_regra, modelo
from src.protocolo import acerto, beta_binomial as beta_post, wilson


# ---------------------------------------------------------------- 1. metricas

def leituras(arv, gold, qid, pred):
    """Tres leituras da mesma predicao. Devolve (literal, estrita, frouxa)."""
    alvos = list(gold.loc[qid, "alvos"])
    central = gold.loc[qid, "tema_central_id"]
    if not pred or not alvos:
        return False, False, False
    literal = acerto(arv, alvos, pred)
    estrita = bool(pred == central or pred in alvos)
    r1 = tema1(arv, central) if central else None
    frouxa = bool(r1 and tema1(arv, pred) == r1)
    return literal, estrita, frouxa


def sensibilidade_metrica(arv, gold, ids, pred, sel, rotulo):
    lit = est = fro = 0
    m = 0
    for i, qid in enumerate(ids):
        if not sel[i]:
            continue
        m += 1
        a, b, c = leituras(arv, gold, qid, pred[i])
        lit, est, fro = lit + a, est + b, fro + c
    return {
        "conjunto": rotulo, "publicadas": m,
        "literal": round(lit / m, 4) if m else None,
        "estrita": round(est / m, 4) if m else None,
        "frouxa": round(fro / m, 4) if m else None,
        "literal_acertos": lit, "estrita_acertos": est, "frouxa_acertos": fro,
    }


# --------------------------------------------------- 2. regras nos mesmos folds

def seleciona_tau(base_tr, s_tr, y_tr, alvo):
    """Maior cobertura no treino com precisao >= alvo. Devolve tau ou None."""
    melhor_t, melhor_m = None, -1
    for t in sorted(set(s_tr[base_tr])):
        sel = base_tr & (s_tr >= t)
        m = int(sel.sum())
        if m == 0 or m <= melhor_m:
            continue
        if y_tr[sel].mean() >= alvo:
            melhor_t, melhor_m = float(t), m
    return melhor_t


def avaliar(base_mask, score, y, folds, alvo=ALVO_PRECISAO):
    """Escolhe o limiar no treino de cada fold e mede no teste (pooled)."""
    pub = np.zeros(len(y), dtype=bool)
    taus = []
    for tr, te in folds[:5]:
        t = seleciona_tau(base_mask[tr], score[tr], y[tr], alvo)
        taus.append(t)
        if t is not None:
            pub[te] |= base_mask[te] & (score[te] >= t)
    m = int(pub.sum())
    ac = int(y[pub].sum())
    lo, hi = wilson(ac, m)
    return {"publicados": m, "acertos": ac,
            "precisao": round(ac / m, 4) if m else None,
            "precisao_lo": round(lo, 4) if m else None,
            "cobertura": round(m / len(y), 4),
            "taus": [None if t is None else round(t, 4) for t in taus], "pub": pub}


def bagging_oof(X, y, folds, B=200, seed=SEED):
    """Logistica com bagging (bootstrap bayesiano nao-parametrico) fora da dobra.

    Devolve a probabilidade media e o desvio medio entre os B reajustes, que serve
    de medida de estabilidade por questao (triagem de quem revisar primeiro).
    """
    rng = np.random.default_rng(seed)
    soma = np.zeros(len(y))
    cnt = np.zeros(len(y))
    sds = []
    for tr, te in folds:
        Xtr = X.iloc[tr].reset_index(drop=True)
        ytr = y[tr]
        ps = np.zeros((B, len(te)))
        for b in range(B):
            idx = rng.integers(0, len(tr), len(tr))
            if len(np.unique(ytr[idx])) < 2:
                idx = np.arange(len(tr))
            clf = modelo().fit(Xtr.iloc[idx], ytr[idx])
            ps[b] = clf.predict_proba(X.iloc[te])[:, 1]
        soma[te] += ps.mean(axis=0)
        cnt[te] += 1
        sds.append(ps.std(axis=0).mean())
    return soma / np.maximum(cnt, 1), float(np.mean(sds))


def p_interno(X, y, folds, k):
    """Probabilidades do treino do fold externo k, sem ver o grupo de teste.

    Treina em 3/4 do treino e prediz o quarto restante; modelo nunca viu o fold
    externo nem a propria questao. E a base honesta para escolher o limiar.
    """
    tr, te = folds[k]
    tr_idx = np.array([i for i in range(len(y)) if i not in set(int(j) for j in te)])
    pos = {int(g): l for l, g in enumerate(tr_idx)}
    p_tr = np.zeros(len(tr_idx))
    for j, (a, b) in enumerate(folds[:5]):
        if j == k:
            continue
        a_in = [pos[int(i)] for i in a if int(i) in pos]
        b_in = [pos[int(i)] for i in b if int(i) in pos]
        if not a_in or not b_in:
            continue
        clf = modelo().fit(X.iloc[tr_idx[a_in]], y[tr_idx[a_in]])
        p_tr[b_in] = clf.predict_proba(X.iloc[tr_idx[b_in]])[:, 1]
    return tr_idx, p_tr, te


def nested_por_selecao(X, y, cons, folds, selecionar):
    """Aninhado honesto: escolhe a regra no treino (sem vazamento) e mede no teste."""
    pub = np.zeros(len(y), dtype=bool)
    regras = []
    for k in range(len(folds[:5])):
        tr_idx, p_tr, te = p_interno(X, y, folds, k)
        lam, c = selecionar(p_tr, cons[tr_idx], y[tr_idx])
        regras.append({"limiar": None if lam is None else round(float(lam), 4), "consenso": c})
        if lam is None:
            continue
        clf = modelo().fit(X.iloc[tr_idx], y[tr_idx])
        p_te = clf.predict_proba(X.iloc[te])[:, 1]
        te_idx = np.array([int(i) for i in te])
        pub[te_idx] |= (cons[te_idx] >= c) & (p_te >= lam)
    m = int(pub.sum())
    ac = int(y[pub].sum())
    lo, hi = wilson(ac, m)
    return {"publicados": m, "acertos": ac,
            "precisao": round(ac / m, 4) if m else None,
            "precisao_lo": round(lo, 4) if m else None,
            "precisao_hi": round(hi, 4) if m else None,
            "cobertura": round(m / len(y), 4), "regras": regras, "pub": pub}


def nested_corrigido(X, y, cons, folds, alvo=ALVO_PRECISAO):
    """Protocolo aninhado corrigido com o criterio classico (cobertura maxima no treino)."""
    return nested_por_selecao(
        X, y, cons, folds,
        lambda p, c, yy: escolher_regra(p, c, yy, alvo),
    )


def nested_certificado(X, y, cons, folds, alpha):
    """Aninhado com o limiar CERTIFICADO no treino (cota de Clopper-Pearson <= alpha)."""
    def sel(p, c, yy):
        lam, _ = certificado(c >= 1.0, p, 1 - yy, alpha)
        return lam, 1.0

    return nested_por_selecao(X, y, cons, folds, sel)


# ---------------------------------------------------------------- 4. beta-binomial

def beta_binomial(ac, m, a0=1.0, b0=1.0):
    r = beta_post(ac, m, a0, b0)
    return {"acertos": r["acertos"], "publicadas": r["publicadas"],
            "media": round(r["media"], 4), "lo": round(r["lo"], 4), "hi": round(r["hi"], 4)}


# ---------------------------------------------------------------- manifesto

def _sha(p):
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def manifesto(tau=None, c_final=1.0):
    def ver(mod):
        try:
            return getattr(__import__(mod), "__version__", "?")
        except Exception:
            return "?"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent,
                                         text=True).strip()
    except Exception:
        commit = "?"
    arquivos = {
        "publicacao.csv": ROOT / "publicacao.csv",
        "previsao.txt": ROOT / "previsao.txt",
        "temas.csv": ROOT / "data" / "temas.csv",
        "folha_verdade.csv": ROOT / "data" / "folha_verdade.csv",
        "questoes.jsonl": ROOT / "data" / "questoes.jsonl",
        "dicionario_juridico.csv": ROOT / "data" / "dicionario_juridico.csv",
    }
    return {
        "commit": commit,
        "python": sys.version.split()[0],
        "plataforma": platform.platform(),
        "pacotes": {m: ver(m) for m in ("numpy", "pandas", "sklearn", "scipy")},
        "seed": SEED, "n_repeats": 5, "n_splits": 5,
        "regra_final": {"consenso_min": c_final, "tau": tau},
        "hash_algoritmo": "sha256 truncado em 16 hex",
        "hashes": {k: (_sha(v) if v.exists() else "ausente") for k, v in arquivos.items()},
    }


# ---------------------------------------------------------------- main

def main():
    b = base()
    arv, gold, ids = b["arv"], b["gold"], b["ids"]
    X, y, cons, p_oof, folds = b["X"], b["y"], b["cons"], b["p_oof"], b["folds"]
    pred = b["pred"]
    out = {}

    # ---- 1. sensibilidade da metrica ------------------------------------
    resumo_dec = json.loads((ARTEFATOS / "decisao_resumo.json").read_text(encoding="utf-8"))
    tau_final = float(resumo_dec["regra"]["tau"])
    c_final = float(resumo_dec["regra"]["consenso_min"])
    sel_final = (cons >= c_final) & (p_oof >= tau_final)
    sel_cons = cons >= c_final
    out["tau_final"] = tau_final
    out["metrica"] = [
        sensibilidade_metrica(arv, gold, ids, pred, sel_final, f"regra final (consenso>={c_final:.2f} e tau={tau_final:.4f})"),
        sensibilidade_metrica(arv, gold, ids, pred, sel_cons, f"consenso>={c_final:.2f} (sem limiar)"),
        sensibilidade_metrica(arv, gold, ids, pred, np.ones(len(y), bool), "publicando tudo"),
    ]

    # ---- 2. regras comparadas nos mesmos folds -------------------------
    p_bag, sd_bag = bagging_oof(X, y, folds)
    regras = {
        "manual: consenso=1": (cons >= 1.0, cons.copy(), None),
        "manual: consenso=1 e rel_pri": (cons >= 1.0, X["rel_pri"].to_numpy(), None),
        "manual: consenso=1 e gap_pri": (cons >= 1.0, X["gap_pri"].to_numpy(), None),
        "manual: consenso=1 e branch_gap": (cons >= 1.0, X["branch_gap"].to_numpy(), None),
        "logistica p_oof": (cons >= 1.0, p_oof, None),
        "logistica bagging": (cons >= 1.0, p_bag, None),
    }
    comp = []
    for nome, (bm, sc, _) in regras.items():
        r = avaliar(bm, np.asarray(sc, float), y, folds)
        comp.append({"regra": nome, "publicados": r["publicados"], "acertos": r["acertos"],
                     "precisao": r["precisao"], "cobertura": r["cobertura"],
                     "precisao_lo": r["precisao_lo"]})
    out["comparacao_regras_nested"] = comp
    out["bagging_sd_media"] = round(sd_bag, 4)

    # ---- 3. protocolo aninhado corrigido -------------------------------
    naive = out["comparacao_regras_nested"][4]
    corr = nested_corrigido(X, y, cons, folds)
    out["aninhado"] = {
        "ingenuo_p_oof_global": {k: naive[k] for k in ("publicados", "acertos", "precisao", "cobertura")},
        "corrigido_sem_vazamento": {k: corr[k] for k in ("publicados", "acertos", "precisao",
                                                         "precisao_lo", "precisao_hi", "cobertura")},
        "regras_por_fold": corr["regras"],
    }
    out["certificado_nested"] = {
        f"alpha_{a}": {k: v for k, v in nested_certificado(X, y, cons, folds, a).items() if k != "pub"}
        for a in (0.10, 0.15, 0.20, 0.25)
    }

    # ---- 4. beta-binomial ---------------------------------------------
    out["beta_binomial"] = {
        "in_sample_19_20": beta_binomial(*sens_contagem(arv, gold, ids, pred, sel_final)),
        "uniforme_referencia": {"19/20": beta_binomial(19, 20), "13/17": beta_binomial(13, 17)},
    }

    # ---- 5. ponto de operacao -----------------------------------------
    pont = pd.read_csv(ARTEFATOS / "pontuacao_659.csv")
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    decisao = pub.set_index("id")["decisao"]
    pub_ids = [i for i in pont["id"] if decisao.get(i) == "publicar"]
    ramo = {}
    for i in pub_ids:
        t = pub.set_index("id")["tema_central_id"].get(i)
        r = arv.raiz(t) if t else "sem_tema"
        ramo[r] = ramo.get(r, 0) + 1
    out["ponto_operacao"] = {
        "publicadas_total": len(pub_ids),
        "por_faixa": pont.set_index("id").loc[pub_ids, "faixa"].value_counts().to_dict(),
        "por_ramo": dict(sorted(ramo.items(), key=lambda kv: -kv[1])),
        "media_p_oof_100": round(float(p_oof.mean()), 4),
        "media_p_all_659": round(float(pont["p"].mean()), 4),
        "media_p_all_antigas": round(float(pont[pont.faixa == "antiga"]["p"].mean()), 4),
        "media_p_all_novas": round(float(pont[pont.faixa == "nova"]["p"].mean()), 4),
    }

    # ---- 6. manifesto --------------------------------------------------
    out["manifesto"] = manifesto(tau_final, c_final)

    (ARTEFATOS / "auditoria.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                                              encoding="utf-8")

    print("=== 1. sensibilidade da metrica hierarquica ===")
    print(pd.DataFrame(out["metrica"]).to_string(index=False))
    print("\n=== 2. regras nos mesmos folds (limiar no treino) ===")
    print(pd.DataFrame(comp).to_string(index=False))
    print(f"\nbagging: desvio medio da probabilidade entre {200} reajustes = {sd_bag:.3f}")
    print("\n=== 3. protocolo aninhado (ingenuo x corrigido) ===")
    print(pd.DataFrame([out["aninhado"]["ingenuo_p_oof_global"],
                        out["aninhado"]["corrigido_sem_vazamento"]]).to_string(index=False))
    print("regras por fold:", out["aninhado"]["regras_por_fold"])
    print("\n--- precisao CERTIFICAVEL, tambem nested (Clopper-Pearson no treino) ---")
    df_cert = pd.DataFrame(out["certificado_nested"]).T.drop(columns=["regras"])
    print(df_cert.to_string())
    print("\n=== 4. beta-binomial ===")
    print(pd.DataFrame([out["beta_binomial"]["in_sample_19_20"] |
                        {"caso": "regra final in-sample"}]).to_string(index=False))
    print("\n=== 5. ponto de operacao ===")
    print(json.dumps(out["ponto_operacao"], ensure_ascii=False, indent=2))
    print("\n=== 6. manifesto ===")
    print(json.dumps(out["manifesto"], ensure_ascii=False, indent=2))


def sens_contagem(arv, gold, ids, pred, sel):
    ac = 0
    m = 0
    for i, qid in enumerate(ids):
        if sel[i]:
            m += 1
            ac += int(acerto(arv, gold.loc[qid, "alvos"], pred[i]))
    return ac, m


if __name__ == "__main__":
    main()
