"""Etapa 5 — ramo em dois estagios, agregacao por ramo e disciplina como prior.

Pergunta: a escolha do ramo melhora se ela for feita em um estagio proprio, com
agregacao dos filhos e com a disciplina de origem como prior — em vez de simplesmente
pegar o ramo do top-1 plano?

O que e medido (92 questoes com tema, texto enriquecido):

  estagio 1 (ramo)
    max        score do ramo = maior score entre seus membros (= ramo do top-1 plano)
    soma3      soma dos 3 melhores membros (premia ramo com varios candidatos bons)
    media      media de todos os membros (penaliza ramo grande)
    prior_l    max normalizado + lambda se a raiz do ramo == disciplina_origem

  estagio 2 (subtema, dentro do ramo escolhido)
    tema@1     fracao em que o top-1 restrito e o tema central
    caso@1     fracao em que o top-1 restrito acerta pela regua do case (tema, pai ou filho)

  decisao final
    publicar o RAMO (nunca o subtema): publicar subtema so perde, porque a regua
    aceita pai e filho, mas nao irmao. O estagio 2 e diagnostico de granularidade.

Uso (da pasta fase2/):
    python -m src.cascata
"""
import numpy as np
import pandas as pd

from src.artefato import tema1
from src.config import ARTEFATOS, SEED
from src.decisao import MAPAD, RETRIEVERS, promover
from src.dicionario import Dicionario
from src.pisos import carregar_enriquecimento, textos
from src.protocolo import (
    acerto,
    carregar_gold,
    carregar_questoes,
    estratos,
    folds_estratificados,
    grupos_duplicados,
    wilson,
)
from src.recuperacao import Busca, ordem_desc, texto_questao
from src.temas import Arvore

B = 2000


def agrega(arv, pool, M, temas1, modo):
    idx = {t: j for j, t in enumerate(pool)}
    out = np.zeros((M.shape[0], len(temas1)))
    for c, t in enumerate(temas1):
        cols = [idx[t]] + [idx[x] for x in arv.filhos.get(t, []) if x in idx]
        sub = M[:, cols]
        if modo == "max":
            out[:, c] = sub.max(axis=1)
        elif modo == "soma3":
            out[:, c] = np.sort(sub, axis=1)[:, -min(3, sub.shape[1]):].sum(axis=1)
        elif modo == "media":
            out[:, c] = sub.mean(axis=1)
        else:
            raise ValueError(modo)
    return out


def normaliza(M):
    m = M.max(axis=1, keepdims=True)
    m[m == 0] = 1.0
    return M / m


def boot(a, b, seed=SEED, b_=B):
    d = np.asarray(a, float) - np.asarray(b, float)
    rng = np.random.default_rng(seed)
    n = len(d)
    s = np.array([d[rng.integers(0, n, n)].mean() for _ in range(b_)])
    return float(np.quantile(s, 0.025)), float(np.quantile(s, 0.975))


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    qmap = q.set_index("id")
    ids = list(gold.index)
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    temas1 = [t for t in arv.ativos.tema_id if arv.nivel[t] == 1]
    dic = Dicionario()
    enr = carregar_enriquecimento()
    tt = textos(arv, pool, dic, enr)["enri"]

    busca = Busca(tt)
    qt = [texto_questao(qmap.loc[i]) for i in ids]
    M = busca.scores("rrf_all", qt)

    validos = [i for i in ids if not gold.loc[i, "fora"]]
    V = [k for k, i in enumerate(ids) if not gold.loc[i, "fora"]]
    pos = {t: j for j, t in enumerate(pool)}

    # ramo aceito e disciplina de origem
    aceitos = {}
    for i in validos:
        aceitos[i] = {tema1(arv, t) for t in gold.loc[i, "alvos"] if tema1(arv, t)}
    disc = {i: MAPAD.get(qmap.loc[i, "disciplina_origem"], "__sem__") for i in validos}
    raiz1 = {t: arv.raiz(t) for t in temas1}

    linhas = []
    vetores = {}
    for modo in ("max", "soma3", "media"):
        Mp = normaliza(agrega(arv, pool, M, temas1, modo))
        for lam in (0.0, 0.02, 0.05, 0.10, 0.20):
            Mp2 = Mp.copy()
            if lam:
                for k in V:
                    for c, t in enumerate(temas1):
                        if raiz1[t] == disc[ids[k]]:
                            Mp2[k, c] += lam
            acertos, cas = [], []
            for k in V:
                ramo = temas1[int(ordem_desc(Mp2[k])[0])]
                acertos.append(1.0 if ramo in aceitos[ids[k]] else 0.0)
                cas.append(1.0 if acerto(arv, gold.loc[ids[k], "alvos"], ramo) else 0.0)
            v = np.array(acertos)
            vetores[(modo, lam)] = v
            lo, hi = wilson(int(v.sum()), len(v))
            linhas.append({
                "modo": modo, "lam": lam,
                "ramo1": round(float(v.mean()), 4),
                "ramo1_lo": round(lo, 4), "ramo1_hi": round(hi, 4),
                "caso1": round(float(np.mean(cas)), 4),
            })

    df = pd.DataFrame(linhas)
    ref = vetores[("max", 0.0)]
    df["delta"] = [round(float(vetores[(r.modo, r.lam)].mean() - ref.mean()), 4) for r in df.itertuples()]
    df["delta_lo"], df["delta_hi"] = 0.0, 0.0
    for r in df.itertuples():
        if (r.modo, r.lam) != ("max", 0.0):
            lo, hi = boot(vetores[(r.modo, r.lam)], ref)
            df.loc[r.Index, "delta_lo"] = round(lo, 4)
            df.loc[r.Index, "delta_hi"] = round(hi, 4)
    df.to_csv(ARTEFATOS / "cascata_ramo.csv", index=False)

    print("=== estagio 1: ramo@1 por agregacao e prior de disciplina (n=92) ===")
    print(df.to_string(index=False))

    # ---- estagio 2: dentro do ramo escolhido (max, sem prior), ranquear so os membros
    Mp = agrega(arv, pool, M, temas1, "max")
    certo_r, certo_c, n = 0, 0, 0
    sub_pub = 0
    for k in V:
        i = ids[k]
        ramo = temas1[int(ordem_desc(Mp[k])[0])]
        membros = [ramo] + [x for x in arv.filhos.get(ramo, []) if x in pos]
        if not membros:
            continue
        j = max(membros, key=lambda t: M[k, pos[t]])
        n += 1
        gold_alvos = gold.loc[i, "alvos"]
        if j in gold_alvos:
            certo_r += 1
        if acerto(arv, gold_alvos, j):
            certo_c += 1
        if acerto(arv, gold_alvos, j) and not acerto(arv, gold_alvos, ramo):
            sub_pub += 1
    print(f"\n=== estagio 2: subtema dentro do ramo (n={n}) ===")
    print(f"  subtema exato (top-1 restrito): {certo_r}/{n} = {certo_r/n:.3f}")
    print(f"  regua do case:                  {certo_c}/{n} = {certo_c/n:.3f}")
    print(f"  ganharia publicando subtema onde o ramo erra: {sub_pub}")

    melhor = df.sort_values("ramo1", ascending=False).iloc[0]
    print(f"\nMelhor estagio 1: {melhor.modo} / lambda={melhor.lam} -> ramo@1={melhor.ramo1:.4f} "
          f"(delta {melhor.delta:+.3f}, IC {melhor.delta_lo:+.3f}..{melhor.delta_hi:+.3f})")
    # ---- validacao aninhada da escolha (modo, lambda)
    # A escolha do prior e do modo e feita em 4/5 e medida no 1/5 que sobra.
    grupos = grupos_duplicados([qmap.loc[i, "texto"] for i in ids])
    est = estratos(gold)
    folds = folds_estratificados(est, grupos, n_splits=5, seed=SEED)
    chaves = list(vetores)
    acertos_nested, escolhas = 0, 0
    for tr, te in folds:
        tr = [k for k in tr if not gold.loc[ids[k], "fora"]]
        te = [k for k in te if not gold.loc[ids[k], "fora"]]
        if not te:
            continue
        # mapa posicao-em-validos -> indice local do vetor
        posv = {k: j for j, k in enumerate(V)}
        melhor = max(
            chaves,
            key=lambda c: np.mean([vetores[c][posv[k]] for k in tr]),
        )
        acertos_nested += int(sum(vetores[melhor][posv[k]] for k in te))
        escolhas += len(te)
    print(f"\n=== escolha honesta de (modo, lambda) por validacao aninhada ===")
    print(f"  ramo@1 aninhado: {acertos_nested}/{escolhas} = {acertos_nested/escolhas:.3f}")
    print(f"  ramo@1 fixo (max, sem prior): {ref.mean():.3f}")
    print(f"Artefato: {ARTEFATOS / 'cascata_ramo.csv'}")


if __name__ == "__main__":
    main()
