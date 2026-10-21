"""Etapa 2, passo 1 — pisos gratuitos (sem LLM) e o teto do enriquecimento.

Pergunta: o texto do tema pode ser melhorado SO com insumo que ja existe
(hierarquia e dicionario), antes de gastar qualquer token?

Variantes de `texto_tema`:
  base        caminho + titulo (definicao atual, igual a Fase 1)
  filhos      base + titulos dos filhos diretos (o ramo "fala" o vocabulario dos filhos)
  dic         base + termos do dicionario que casam com o texto do tema
  filhos+dic  as duas coisas
  enri        base + sinonimos + institutos + texto do enriquecimento_v01
  tudo        filhos + dic + enri

Metricas (92 questoes com tema; as 8 fora ficam de fora, como em `ramo@1`):
  ramo@1      tema de nivel 1 do top-1 == tema de nivel 1 do gabarito
  ramo@1 lo/hi intervalo de Wilson
  delta       diferenca pareada contra a base, com IC bootstrap
  prec@0.20   precisao frouxa (mesmo ramo) publicando os 20% de maior `rel`
  lit@0.20    idem, regua literal do case

Uso (da pasta fase2/):
    python -m src.pisos
"""
import json

import numpy as np
import pandas as pd

from src.artefato import tema1
from src.config import ARTEFATOS, DATA, SEED
from src.dicionario import Dicionario
from src.protocolo import acerto, carregar_gold, carregar_questoes, wilson
from src.recuperacao import RETRIEVERS, Busca, sinais, texto_questao, texto_tema
from src.temas import Arvore

B = 2000  # reamostragens do bootstrap pareado


def carregar_enriquecimento():
    p = ARTEFATOS.parent / "enriquecimento_v01.jsonl"
    out = {}
    if not p.exists():
        return out
    for linha in p.read_text(encoding="utf-8").splitlines():
        if not linha.strip():
            continue
        o = json.loads(linha)
        out[str(o["id_tema"])] = o
    return out


def textos(arv, pool, dic, enr):
    """Devolve {variante: [texto por tema do pool]}."""
    base = {t: texto_tema(arv, t) for t in pool}
    filhos = {
        t: (base[t] + " " + " ".join(
            arv.titulo[c] for c in arv.filhos.get(t, []) if arv.publicavel(c)
        )).strip()
        for t in pool
    }
    comdic = {t: dic.expandir(base[t]) for t in pool}
    fd = {t: (filhos[t] + " " + dic.expandir(base[t])).strip() for t in pool}
    enri = {}
    campos = {k: {} for k in ("sin", "inst", "texto")}
    for t in pool:
        o = enr.get(t)
        if not o:
            enri[t] = base[t]
            for k in campos:
                campos[k][t] = ""
            continue
        sin = " ".join(o.get("sinonimos", []))
        inst = " ".join(o.get("institutos", []))
        txt = o.get("texto_enriquecido", "")
        campos["sin"][t], campos["inst"][t], campos["texto"][t] = sin, inst, txt
        enri[t] = (base[t] + " " + " ".join([sin, inst, txt])).strip()
    tudo = {t: (filhos[t] + " " + dic.expandir(base[t]) + " " + enri[t]).strip() for t in pool}

    def junta(quais):
        return [(base[t] + " " + " ".join(campos[k][t] for k in quais)).strip() for t in pool]

    out = {
        "base": [base[t] for t in pool],
        "filhos": [filhos[t] for t in pool],
        "dic": [comdic[t] for t in pool],
        "filhos+dic": [fd[t] for t in pool],
        "enri": [enri[t] for t in pool],
        "tudo": [tudo[t] for t in pool],
        # ablação por campo
        "so_sin": junta(["sin"]),
        "so_inst": junta(["inst"]),
        "so_texto": junta(["texto"]),
        "sin+inst": junta(["sin", "inst"]),
        "sin+texto": junta(["sin", "texto"]),
        "inst+texto": junta(["inst", "texto"]),
    }
    return out


def ramos_de_acerto(arv, gold, qid):
    """Ramos (nivel 1) aceitos para a questao. Vazio se fora da taxonomia."""
    if gold.loc[qid, "fora"]:
        return set()
    out = set()
    for t in gold.loc[qid, "alvos"]:
        r = tema1(arv, t)
        if r:
            out.add(r)
    return out


def bootstrap_delta(a, b, seed=SEED, b_=B):
    """IC 95% da diferenca pareada (a - b) por reamostragem das questoes."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    rng = np.random.default_rng(seed)
    n = len(d)
    amostras = np.array([d[rng.integers(0, n, n)].mean() for _ in range(b_)])
    return float(np.quantile(amostras, 0.025)), float(np.quantile(amostras, 0.975))


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    ids = list(gold.index)
    qmap = q.set_index("id")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    dic = Dicionario()
    enr = carregar_enriquecimento()

    validos = [i for i in ids if not gold.loc[i, "fora"]]
    aceitos = {i: ramos_de_acerto(arv, gold, i) for i in validos}
    qt = [texto_questao(qmap.loc[i]) for i in ids]

    print(f"questoes: {len(ids)} | com tema: {len(validos)} | enriquecidos: {len(enr)}/{len(pool)}")
    print("pisos: ramo@1 mede so a escolha do ramo (nivel 1), que e onde o sistema responde\n")

    variantes = textos(arv, pool, dic, enr)
    linhas, vetores = [], {}
    for nome, tt in variantes.items():
        busca = Busca(tt)
        for ret in RETRIEVERS:
            M = busca.scores(ret, qt)
            pos = {t: j for j, t in enumerate(pool)}
            acertos = []
            for i in validos:
                pred = pool[sinais(M, ids.index(i))["idx_top1"]]
                acertos.append(1.0 if tema1(arv, pred) in aceitos[i] else 0.0)
            acertos = np.array(acertos)
            vetores[(nome, ret)] = acertos

            # precisao na cobertura fixa de 20% (sinal `rel`, o mais estavel)
            rel = np.array([sinais(M, ids.index(i))["rel"] for i in validos])
            k = max(1, int(round(0.20 * len(validos))))
            top = np.argsort(-rel)[:k]
            lit = np.array([
                1.0 if acerto(arv, gold.loc[validos[j], "alvos"], pool[sinais(M, ids.index(validos[j]))["idx_top1"]]) else 0.0
                for j in top
            ])
            frouxa = acertos[top]
            lo, hi = wilson(int(frouxa.sum()), k)
            linhas.append({
                "variante": nome,
                "recuperador": ret,
                "ramo1": round(float(acertos.mean()), 4),
                "ramo1_lo": round(lo, 4) if False else None,
                "n": len(validos),
                "prec_frouxa_020": round(float(frouxa.mean()), 4),
                "prec_frouxa_020_lo": round(lo, 4),
                "prec_lit_020": round(float(lit.mean()), 4),
                "k20": k,
            })

    df = pd.DataFrame(linhas)
    # IC de Wilson para ramo@1 e delta pareado contra a base
    ramo_lo, ramo_hi, delta, d_lo, d_hi = [], [], [], [], []
    for r in df.itertuples():
        v = vetores[(r.variante, r.recuperador)]
        lo, hi = wilson(int(v.sum()), len(v))
        ramo_lo.append(round(lo, 4))
        ramo_hi.append(round(hi, 4))
        b = float(vetores[("base", r.recuperador)].mean())
        delta.append(round(float(v.mean()) - b, 4))
        if r.variante == "base":
            d_lo.append(0.0)
            d_hi.append(0.0)
        else:
            lo2, hi2 = bootstrap_delta(v, vetores[("base", r.recuperador)])
            d_lo.append(round(lo2, 4))
            d_hi.append(round(hi2, 4))
    df["ramo1_lo"] = ramo_lo
    df["ramo1_hi"] = ramo_hi
    df["delta"] = delta
    df["delta_lo"] = d_lo
    df["delta_hi"] = d_hi

    df.to_csv(ARTEFATOS / "pisos.csv", index=False)

    print("=== ramo@1 por variante de texto do tema ===")
    tab = df.pivot(index="variante", columns="recuperador", values="ramo1")
    ordem = ["base", "filhos", "dic", "filhos+dic", "enri", "tudo",
             "so_sin", "so_inst", "so_texto", "sin+inst", "sin+texto", "inst+texto"]
    print(tab.loc[[o for o in ordem if o in tab.index]].to_string())

    print("\n=== melhor variante por recuperador (delta vs base, IC bootstrap) ===")
    melhor = (
        df.sort_values("ramo1", ascending=False)
        .groupby("recuperador", as_index=False)
        .first()
        .sort_values("ramo1", ascending=False)
    )
    print(melhor[["recuperador", "variante", "ramo1", "ramo1_lo", "ramo1_hi", "delta", "delta_lo", "delta_hi", "prec_frouxa_020", "prec_lit_020"]].to_string(index=False))

    print("\n=== criterio de entrada (ramo@1 >= melhor piso + 0,05) ===")
    pisos_livres = df[df.variante.isin(["base", "filhos", "dic", "filhos+dic"])]
    piso = float(pisos_livres.ramo1.max())
    ref = pisos_livres.loc[pisos_livres.ramo1.idxmax()]
    print(f"melhor piso gratuito: {piso:.4f} ({ref.variante} / {ref.recuperador}) -> alvo >= {piso + 0.05:.4f}")
    passam = df[(df.ramo1 >= piso + 0.05)].sort_values("ramo1", ascending=False)
    if len(passam):
        for r in passam.itertuples():
            print(f"  ATENDE {r.variante:12s} / {r.recuperador:15s} ramo@1={r.ramo1:.4f} "
                  f"(delta {r.delta:+.3f}, IC {r.delta_lo:+.3f}..{r.delta_hi:+.3f}; "
                  f"prec@20% {r.prec_frouxa_020:.2f})")
    else:
        print("  nenhuma variante atinge o criterio")
    print(f"\nArtefato: {ARTEFATOS / 'pisos.csv'}")


if __name__ == "__main__":
    main()
