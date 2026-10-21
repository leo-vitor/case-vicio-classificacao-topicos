"""Experimento 5 — regra final: curva precisao x cobertura e robustez.

Perguntas:
  1. A regra entregue (consenso >= 0,75 e p >= tau) esta num ponto razoavel da
     curva, ou foi um pico de sorte?
  2. Quanto a precisao e a cobertura variam se os 100 rotulos fossem outros 100
     (bootstrap)? E se tau mudasse 0,02?
  3. Qual a maior cobertura com erro certificavel a 5/10/15/20% (Clopper-Pearson)?

Usa a probabilidade fora da dobra (`p_oof`), que e a grandeza usada para escolher
a regra. Nada aqui e escolhido por LLM.

Saida: `artefatos/regra_final.json` + resumo no terminal.

Uso (da pasta fase2/):
    python -m src.regra_final
"""
import json

import numpy as np

from src.artefato import base
from src.config import ARTEFATOS, SEED
from src.decisao import ALVO_PRECISAO
from src.protocolo import wilson
from scipy.stats import beta as beta_dist

CONS = (1.0, 0.75, 0.5, 0.25)
ALPHAS = (0.05, 0.10, 0.15, 0.20, 0.25)
COBERTURAS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
B = 2000


def cp_upper(erros, n, alpha):
    """Cota superior de Clopper-Pearson (unilateral) do erro, confianca 1-alpha.

    Mesma definicao de `src/conformal.py` (`clopper_upper`), para que a fronteira
    daqui e a de la sejam comparaveis.
    """
    if n == 0:
        return None
    if erros >= n:
        return 1.0
    if erros == 0:
        return 1 - alpha ** (1 / n)
    return float(beta_dist.ppf(1 - alpha, erros + 1, n - erros))


def avaliar(p, cons, y, tau, c):
    sel = (cons >= c) & (p >= tau)
    n = int(sel.sum())
    a = int(y[sel].sum())
    return n, a


def main():
    b = base()
    p, cons, y = b["p_oof"], b["cons"], np.asarray(b["y"], dtype=float)
    regra = json.loads((ARTEFATOS / "decisao_resumo.json").read_text(encoding="utf-8"))["regra"]
    tau, c = float(regra["tau"]), float(regra["consenso_min"])
    n0, a0 = avaliar(p, cons, y, tau, c)
    lo0, hi0 = wilson(a0, n0)

    # --- curva completa (c fixo no entregue) ------------------------------
    curva = []
    for t in sorted(set(np.round(p, 10)), reverse=True):
        n, a = avaliar(p, cons, y, t, c)
        if n == 0:
            continue
        lo, hi = wilson(a, n)
        curva.append({"tau": round(float(t), 6), "publicadas": n, "acertos": a,
                      "precisao": round(a / n, 4), "cobertura": round(n / len(y), 4),
                      "precisao_lo": round(lo, 4), "precisao_hi": round(hi, 4)})

    # --- pontos em coberturas de referencia -------------------------------
    marcos = []
    for alvo in COBERTURAS:
        ok = [x for x in curva if x["cobertura"] >= alvo - 1e-9]
        if not ok:
            continue
        x = max(ok, key=lambda z: z["precisao"])
        marcos.append({"cobertura_alvo": alvo, **x})
    marcos.append({"cobertura_alvo": round(n0 / len(y), 4), **{
        "tau": tau, "publicadas": n0, "acertos": a0, "precisao": round(a0 / n0, 4),
        "cobertura": round(n0 / len(y), 4), "precisao_lo": round(lo0, 4),
        "precisao_hi": round(hi0, 4), "entregue": True}})

    # --- fronteira certificavel (Clopper-Pearson) ------------------------
    certificavel = []
    for alpha in ALPHAS:
        melhor = None
        for x in curva:
            upper = cp_upper(x["publicadas"] - x["acertos"], x["publicadas"], alpha)
            if upper is not None and upper <= alpha:
                if melhor is None or x["cobertura"] > melhor["cobertura"]:
                    melhor = {**x, "cota_superior_erro": round(upper, 4), "alpha": alpha}
        if melhor:
            certificavel.append(melhor)

    # --- bootstrap dos 100 rotulos (regra fixa) --------------------------
    rng = np.random.default_rng(SEED)
    precs, covs = [], []
    for _ in range(B):
        idx = rng.integers(0, len(y), len(y))
        n = int(((cons[idx] >= c) & (p[idx] >= tau)).sum())
        if n == 0:
            continue
        precs.append(float(y[idx][(cons[idx] >= c) & (p[idx] >= tau)].sum()) / n)
        covs.append(n / len(y))
    boot = {
        "precisao": {"media": round(float(np.mean(precs)), 4),
                     "lo": round(float(np.quantile(precs, 0.025)), 4),
                     "hi": round(float(np.quantile(precs, 0.975)), 4)},
        "cobertura": {"media": round(float(np.mean(covs)), 4),
                      "lo": round(float(np.quantile(covs, 0.025)), 4),
                      "hi": round(float(np.quantile(covs, 0.975)), 4)},
        "n_boot": B,
    }

    # --- sensibilidade a tau ---------------------------------------------
    sens = []
    for d in (-0.04, -0.02, -0.01, 0.0, 0.01, 0.02, 0.04):
        n, a = avaliar(p, cons, y, tau + d, c)
        sens.append({"tau": round(tau + d, 6), "delta": d, "publicadas": n, "acertos": a,
                     "precisao": round(a / n, 4) if n else None,
                     "cobertura": round(n / len(y), 4)})

    saida = {
        "regra": {"tau": tau, "consenso_min": c, "alvo_precisao": ALVO_PRECISAO},
        "ponto": {"publicadas": n0, "acertos": a0, "precisao": round(a0 / n0, 4),
                  "cobertura": round(n0 / len(y), 4),
                  "wilson_lo": round(lo0, 4), "wilson_hi": round(hi0, 4)},
        "marcos": marcos, "certificavel": certificavel, "bootstrap": boot,
        "sensibilidade_tau": sens, "curva": curva,
    }
    (ARTEFATOS / "regra_final.json").write_text(
        json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== ponto entregue ===")
    print(f"  tau={tau:.6f} cons>={c} -> {a0}/{n0} = {a0/n0:.3f} "
          f"[{lo0:.3f}; {hi0:.3f}], cobertura {n0/len(y):.3f}")
    print("\n=== curva: melhor precisao em cada cobertura (c fixo) ===")
    for x in marcos:
        tag = " <- entregue" if x.get("entregue") else ""
        print(f"  cobertura >= {x['cobertura_alvo']:.2f}: tau={x['tau']:.4f} "
              f"{x['acertos']}/{x['publicadas']} = {x['precisao']:.3f} "
              f"(cobertura {x['cobertura']:.3f}){tag}")
    print("\n=== fronteira certificavel (Clopper-Pearson) ===")
    for x in certificavel:
        print(f"  erro <= {x['alpha']:.0%}: {x['acertos']}/{x['publicadas']} = "
              f"{x['precisao']:.3f} (cota {x['cota_superior_erro']:.3f}), "
              f"cobertura {x['cobertura']:.3f}")
    print("\n=== bootstrap dos 100 rotulos (regra fixa) ===")
    print(f"  precisao {boot['precisao']['media']:.3f} "
          f"[{boot['precisao']['lo']:.3f}; {boot['precisao']['hi']:.3f}]")
    print(f"  cobertura {boot['cobertura']['media']:.3f} "
          f"[{boot['cobertura']['lo']:.3f}; {boot['cobertura']['hi']:.3f}]")
    print("\n=== sensibilidade a tau ===")
    for x in sens:
        print(f"  tau{x['delta']:+.2f} -> {x['acertos']}/{x['publicadas']} "
              f"prec={x['precisao']} cov={x['cobertura']:.3f}")
    print("\nartefato:", ARTEFATOS / "regra_final.json")


if __name__ == "__main__":
    main()
