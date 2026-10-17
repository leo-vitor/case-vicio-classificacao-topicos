"""Predicao seletiva calibrada (sem chamadas de API).

  python -m src.experimentos.seletiva curva    escolhe o limiar na metade de calibracao,
                                  avalia na metade de validacao e escreve a curva
  python -m src.experimentos.seletiva aplicar  escreve outputs/publicacao_seletiva.csv
  python -m src.experimentos.seletiva apply    idem, mas sobrescreve publicacao.csv (cuidado)

Ideia (Classificacao Seletiva / Learning to Reject):
  - cada questao tem um score de certeza s(x) em [0,1];
  - publicamos quando s(x) >= t;
  - escolhemos t para maximizar a cobertura sujeita a precisao estimada >= 95%;
  - a precisao e medida so sobre as publicadas, com a regua pai/filho do case.

Nao promovemos questoes que hoje estao em revisar (a menos que --promote seja
passado). O objetivo e proteger a precisao: so rebaixamos.

Fontes:
  Geifman & El-Yaniv (2017), Selective Classification for Deep Neural Networks.
  Angelopoulos et al. (2024), Conformal Risk Control.
  Hierarchical Selective Classification (2024), arXiv:2405.11533.
"""
import argparse
import json
from math import sqrt

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import OUT, ROOT
from src.estimate import wilson
from src.temas import Arvore

CURVA = OUT / "curva_precisao_cobertura.csv"
RESUMO = OUT / "seletiva_resumo.json"
SAIDA = OUT / "publicacao_seletiva.csv"
# Snapshot das decisoes ANTES de aplicar a politica seletiva. Calibramos e
# reaplicamos sempre sobre ele, para que rodar de novo nao "aninha" rebaixamentos.
BASELINE = OUT / "publicacao_congelada.csv"
ALVO = 0.95
B = 300


def _baseline_path():
    return BASELINE if BASELINE.exists() else ROOT / "publicacao.csv"


def _baseline():
    return pd.read_csv(_baseline_path(), dtype=str).fillna("")


def _labeled(arv):
    """Amostra rotulada restrita as publicadas no baseline, com o campo certo
    (regua pai/filho). Nao depende do publicacao.csv atual, para idempotencia."""
    rot = pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")
    rot = rot[rot["tema_correto_id"] != ""]
    base = _baseline().set_index("id")
    linhas = []
    for r in rot.itertuples():
        if r.id not in base.index or base.loc[r.id, "decisao"] != "publicar":
            continue
        tema = base.loc[r.id, "tema_central_id"]
        linhas.append(
            {
                "id": r.id,
                "parte": getattr(r, "parte", ""),
                "incerto": getattr(r, "incerto", ""),
                "tema_correto_id": r.tema_correto_id,
                "certo": r.tema_correto_id != "fora" and arv.relacionado(tema, r.tema_correto_id),
            }
        )
    return pd.DataFrame(linhas)


def _votos():
    return {r["id"]: r["votes"] for r in (json.loads(l) for l in open(OUT / "votos.jsonl", encoding="utf-8"))}


def _sim_chosen(arv, pub):
    """Similaridade TF-IDF entre o texto da questao e o texto do tema escolhido.
    Reconstroi o mesmo tipo de vetor usado em src/candidates.py (lexical 1-2)."""
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    pos = {t: i for i, t in enumerate(pool)}
    q_texts = q["texto"].tolist()
    t_texts = [arv.caminho[t].replace(">", " ") + " " + arv.titulo[t] for t in pool]
    vec = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    vec.fit(q_texts + t_texts)
    Q = vec.transform(q_texts)
    T = vec.transform(t_texts)
    sim = cosine_similarity(Q, T)
    out = {}
    for i, qid in enumerate(q.index):
        t = pub.get(qid, {}).get("tema_central_id", "") if isinstance(pub, dict) else pub.loc[qid, "tema_central_id"]
        out[qid] = float(sim[i, pos[t]]) if t in pos else 0.0
    return out


def _features():
    arv = Arvore()
    votes = _votos()
    ag = pd.read_csv(OUT / "agregado.csv", dtype=str).fillna("")
    agmap = ag.set_index("id")["kind"].to_dict()
    pub = _baseline()
    pubmap = pub.set_index("id")
    gem = arv.gemeos()
    sims = _sim_chosen(arv, pubmap)
    linhas = []
    for qid, vs in votes.items():
        validos = [v for v in vs if not v.get("fora") and v.get("tema_id")]
        foras = [v for v in vs if v.get("fora")]
        n = len(vs)
        cont = {}
        confs = []
        for v in validos:
            cont[v["tema_id"]] = cont.get(v["tema_id"], 0) + 1
            confs.append(float(v.get("conf") or 0))
        if cont:
            topo, cnt = max(cont.items(), key=lambda kv: kv[1])
            agree = cnt / n
            conf_mean = sum(confs) / len(confs)
        else:
            topo, cnt, agree, conf_mean = "", 0, 0.0, 0.0
        score = conf_mean * agree
        tema = pubmap.loc[qid, "tema_central_id"] if qid in pubmap.index else topo
        linhas.append(
            {
                "id": qid,
                "decisao": pubmap.loc[qid, "decisao"] if qid in pubmap.index else "",
                "tema": tema,
                "topo_votos": topo,
                "agree": round(agree, 4),
                "conf_mean": round(conf_mean, 4),
                "n_fora": len(foras),
                "n_validos": len(validos),
                "kind": agmap.get(qid, ""),
                "gemeo": tema in gem,
                "sim": round(sims.get(qid, 0.0), 4),
                "score": round(score, 4),
            }
        )
    return pd.DataFrame(linhas)


def _com_scores(feat, base="score", usar_sim=False, regra="score"):
    f = feat.copy()
    if regra == "mesmo_ramo":
        # A regua do case aceita publicar no pai quando os votos divergem entre
        # subtemas do mesmo ramo. O no comum e seguro por construcao; damos a ele
        # o score maximo e deixamos o limiar agir sobre os demais.
        f["s"] = np.where(f["kind"] == "mesmo_ramo", 1.0, f["score"])
    elif usar_sim or regra == "sim":
        f["s"] = f["score"] * f["sim"]
    else:
        f["s"] = f[base]
    return f


def _split(lab):
    """Divide a amostra rotulada em calibracao e validacao.

    Linhas com `parte` explicito vao para o lado indicado. Linhas sem `parte`
    (tipicamente o censo do grupo A, acrescentado depois) sao distribuidas de
    forma deterministica entre as duas metades, para nao serem descartadas.
    """
    if "parte" in lab.columns:
        cal = lab[lab["parte"] == "calibracao"]
        val = lab[lab["parte"] == "validacao"]
        resto = lab[~lab["parte"].isin(["calibracao", "validacao"])]
        if len(resto):
            resto = resto.sort_values("id")
            meio = (len(resto) + 1) // 2
            cal = pd.concat([cal, resto.iloc[:meio]])
            val = pd.concat([val, resto.iloc[meio:]])
        if len(cal) and len(val):
            return cal, val
    lab = lab.sample(frac=1.0, random_state=42)
    corte = len(lab) // 2
    return lab.iloc[:corte], lab.iloc[corte:]


def _prec(sel):
    n = len(sel)
    k = int(sel["certo"].sum())
    lo, hi = wilson(k, n) if n else (0.0, 1.0)
    return k, n, (k / n if n else 0.0), lo, hi


def curva(usar_sim=False, verbose=True, regra="score"):
    arv = Arvore()
    pubdf = _labeled(arv)
    feat = _com_scores(_features(), usar_sim=usar_sim, regra=regra)
    pubdf = pubdf.merge(feat[["id", "s", "kind", "gemeo", "sim", "score", "agree", "conf_mean", "n_fora"]], on="id", how="left")
    cal, val = _split(pubdf)
    base = _baseline()
    total = len(base)
    n_pub_hoje = int((base["decisao"] == "publicar").sum())
    linhas = []
    grade = np.round(np.arange(0.50, 1.0001, 0.005), 3)
    for t in grade:
        t = float(t)
        sele = feat[(feat["s"] >= t) & (feat["decisao"] == "publicar")]
        k, n, p, lo, hi = _prec(cal[cal["s"] >= t])
        kv, nv, pv, lov, hiv = _prec(val[val["s"] >= t])
        cov = len(sele) / total
        linhas.append(
            {
                "t": round(t, 3),
                "n_pub_total": int(len(sele)),
                "cobertura": round(cov, 4),
                "cal_n": n,
                "cal_prec": round(p, 4),
                "cal_lo": round(lo, 4),
                "val_n": nv,
                "val_prec": round(pv, 4),
                "val_lo": round(lov, 4),
            }
        )
    df = pd.DataFrame(linhas)
    df.to_csv(CURVA, index=False)

    # criterio 1: cobertura maxima com precisao pontual >= ALVO na calibracao e
    # evidencia minima (>= 8 itens). criterio 2 (sem viavel): maior limite
    # inferior de Wilson, para nao escolher um canto com 3 itens.
    MIN_N = 8
    viaveis = df[(df["cal_n"] >= MIN_N) & (df["cal_prec"] >= ALVO)]
    if len(viaveis):
        escolhido = viaveis.sort_values(["cobertura", "cal_prec"], ascending=False).iloc[0]
        criterio = "cobertura_max_com_prec_cal>=0.95"
    else:
        com_n = df[df["cal_n"] >= MIN_N]
        base = com_n if len(com_n) else df
        escolhido = base.sort_values(["cal_lo", "cal_prec", "cobertura"], ascending=False).iloc[0]
        criterio = "sem_limiar_atinge_0.95: maior limite inferior de Wilson (n>=8)"

    t = float(escolhido["t"])

    # cobertura global e intervalo por bootstrap das linhas de calibracao
    def _aplica(tt, base=None):
        base = feat if base is None else base
        sel = base[(base["s"] >= tt) & (base["decisao"] == "publicar")]
        return len(sel) / total

    cob = _aplica(t)
    rng = np.random.default_rng(42)
    cobs = []
    for _ in range(B):
        amostra_cal = cal.sample(frac=1.0, replace=True, random_state=int(rng.integers(1 << 30)))
        t_b = _escolhe(amostra_cal, df) if len(amostra_cal) else t
        cobs.append(_aplica(t_b))
    cobs = np.array(cobs)
    cob_lo = float(min(cob, np.quantile(cobs, 0.025)))
    cob_hi = float(max(cob, np.quantile(cobs, 0.975)))

    sel_final = feat[(feat["s"] >= t) & (feat["decisao"] == "publicar")]
    k_cal, n_cal, p_cal, lo_cal, hi_cal = _prec(cal[cal["s"] >= t])
    k_val, n_val, p_val, lo_val, hi_val = _prec(val[val["s"] >= t])
    resumo = {
        "threshold": t,
        "criterio": criterio,
        "usa_sim": usar_sim,
        "regra": regra,
        "n_publicadas_hoje": n_pub_hoje,
        "n_publicadas_seletiva": int(len(sel_final)),
        "cobertura": round(cob, 4),
        "cobertura_lo": round(cob_lo, 4),
        "cobertura_hi": round(cob_hi, 4),
        "metodo_cobertura": f"bootstrap B={B} das linhas de calibracao, re-escolhendo o limiar",
        "cal_n": n_cal, "cal_prec": round(p_cal, 4), "cal_lo": round(lo_cal, 4),
        "val_n": n_val, "val_prec": round(p_val, 4), "val_lo": round(lo_val, 4),
        "previsao_prec": round(min(p_cal, p_val) if n_val else p_cal, 4),
    }
    RESUMO.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        print(f"Limiar escolhido: {t:.3f} ({criterio})")
        print(f"Calibracao: {k_cal}/{n_cal} = {p_cal:.3f} (lo {lo_cal:.3f})")
        print(f"Validacao:  {k_val}/{n_val} = {p_val:.3f} (lo {lo_val:.3f})")
        print(f"Cobertura:  {cob:.3f} (IC bootstrap {cob_lo:.3f}-{cob_hi:.3f}); hoje {n_pub_hoje} publicadas")
        print(f"Curva em {CURVA}; resumo em {RESUMO}")
    return resumo, df


def _escolhe(cal_boot, df_ref):
    """Escolhe o limiar numa replica bootstrap da calibracao (mesma politica)."""
    linhas = []
    for t in np.round(np.arange(0.50, 1.0001, 0.01), 3):
        t = float(t)
        sel = cal_boot[cal_boot["s"] >= t]
        k, n, p, lo, hi = _prec(sel)
        if n >= 8:
            linhas.append((t, len(sel), p, lo))
    if not linhas:
        return float(df_ref["t"].iloc[-1])
    viaveis = [x for x in linhas if x[2] >= ALVO]
    if viaveis:
        return float(max(viaveis, key=lambda x: (x[1], x[2]))[0])
    return float(max(linhas, key=lambda x: (x[3], x[2], x[1]))[0])


def aplicar(write=False, promote=False, usar_sim=False, regra="score"):
    """Gera publicacao_seletiva.csv (e, opcionalmente, sobrescreve publicacao.csv)."""
    resumo, _ = curva(usar_sim=usar_sim, verbose=False, regra=regra)
    t = resumo["threshold"]
    feat = _com_scores(_features(), usar_sim=usar_sim, regra=regra)
    pub = _baseline()
    fmap = feat.set_index("id")
    linhas = []
    mudou = 0
    for r in pub.itertuples():
        dec = r.decisao
        motivo = r.motivo
        if r.id in fmap.index and dec == "publicar":
            s = float(fmap.loc[r.id, "s"])
            if s < t:
                dec = "revisar"
                motivo = f"seletiva: certeza {s:.2f} < limiar {t:.2f}"
                mudou += 1
        elif promote and r.id in fmap.index and dec == "revisar":
            s = float(fmap.loc[r.id, "s"])
            if s >= t:
                dec = "publicar"
                motivo = ""
                mudou += 1
        linhas.append(
            {
                "id": r.id,
                "decisao": dec,
                "tema_central_id": r.tema_central_id,
                "extras_ids": r.extras_ids,
                "confianca": r.confianca,
                "motivo": motivo,
            }
        )
    out = pd.DataFrame(linhas)
    out.to_csv(SAIDA, index=False)
    print(f"publicacao_seletiva.csv: {len(out)} linhas, {mudou} mudancas, limiar {t:.3f}")
    print(out["decisao"].value_counts().to_dict())
    if write:
        out.to_csv(ROOT / "publicacao.csv", index=False)
        print("publicacao.csv sobrescrito.")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["curva", "aplicar", "apply"], nargs="?", default="curva")
    ap.add_argument("--sim", action="store_true", help="usar score * similaridade do tema escolhido")
    ap.add_argument("--rule", choices=["score", "sim", "mesmo_ramo"], default="score",
                    help="regra de score; 'mesmo_ramo' forca publicar no no comum do ramo")
    ap.add_argument("--promote", action="store_true", help="permitir promover revisar -> publicar")
    args = ap.parse_args()
    if args.cmd == "curva":
        curva(usar_sim=args.sim, regra=args.rule)
    elif args.cmd == "aplicar":
        aplicar(write=False, promote=args.promote, usar_sim=args.sim, regra=args.rule)
    else:
        aplicar(write=True, promote=args.promote, usar_sim=args.sim, regra=args.rule)
