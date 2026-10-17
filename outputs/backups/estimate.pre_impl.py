"""Etapa 5: estimar a precisao das publicadas sem gabarito.

  python -m src.estimate sample     amostra estratificada para rotular as cegas
  python -m src.estimate completar  usa uma amostra ja rotulada: cria os grupos e acrescenta o grupo A que faltar
  python -m src.estimate evaluate   precisao por grupo e total
  python -m src.estimate previsao   escreve previsao.txt (rascunho)

Grupos de publicadas:
  A = publicadas so depois do fallback com a arvore inteira (grupo de maior risco): rotulado por inteiro.
  B = demais publicadas: amostra aleatoria.
O grupo de cada questao fica em outputs/amostra_grupos.csv (nao abra enquanto rotula).
"""
import sys
from math import sqrt

import pandas as pd

from src.config import OUT, ROOT
from src.temas import Arvore

N_AMOSTRA = 80
SEED = 42
ROTULOS = OUT / "amostra_rotulagem.csv"
GRUPOS = OUT / "amostra_grupos.csv"
ANTES = OUT / "antes_fallback" / "publicacao.csv"


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def publicadas():
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    antes = pd.read_csv(ANTES, dtype=str).fillna("").set_index("id")
    p = pub[pub["decisao"] == "publicar"].copy()
    p["grupo"] = ["A" if antes.loc[i, "decisao"] != "publicar" else "B" for i in p["id"]]
    return p


def sample():
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")
    p = publicadas()
    a = p[p["grupo"] == "A"]
    b = p[p["grupo"] == "B"].sample(N_AMOSTRA - len(a), random_state=SEED)
    s = pd.concat([a, b]).sample(frac=1, random_state=SEED)
    pd.DataFrame(
        {
            "id": s["id"].values,
            "texto": [q.loc[i, "texto"][:1800] for i in s["id"]],
            "tema_correto_id": "",
            "incerto": "",
        }
    ).to_csv(ROTULOS, index=False)
    s[["id", "grupo"]].to_csv(GRUPOS, index=False)
    arv = Arvore()
    arv.ativos[arv.ativos.nivel >= 1][["tema_id", "caminho"]].to_csv(OUT / "temas_referencia.csv", index=False)
    print(f"Amostra de {len(s)} em {ROTULOS}: grupo A inteiro ({len(a)}) + {len(s) - len(a)} do grupo B.")
    print("Preencha tema_correto_id ('fora' se nenhum serve; incerto=1 se tiver duvida).")
    print("Nao abra publicacao.csv nem amostra_grupos.csv enquanto rotula.")


def completar():
    """Aproveita uma amostra ja rotulada (de um 'sample' anterior): cria o arquivo de grupos e acrescenta,
    para rotular, as publicadas do grupo A que ficaram de fora da amostra."""
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")
    rot = pd.read_csv(ROTULOS, dtype=str).fillna("")
    p = publicadas()
    g = p.set_index("id")["grupo"]
    novos = p[(p["grupo"] == "A") & ~p["id"].isin(rot["id"])]
    extra = pd.DataFrame({"id": novos["id"].values, "texto": [q.loc[i, "texto"][:1800] for i in novos["id"]], "tema_correto_id": "", "incerto": ""})
    out = pd.concat([rot, extra], ignore_index=True).fillna("")
    out.to_csv(ROTULOS, index=False)
    ok = out[out["id"].isin(g.index)]
    pd.DataFrame({"id": ok["id"].values, "grupo": [g[i] for i in ok["id"]]}).to_csv(GRUPOS, index=False)
    na = int((g[ok["id"]] == "A").sum())
    print(f"Amostra: {len(rot)} linhas ja existentes; {len(rot) - int(rot['id'].isin(g.index).sum())} nao estao mais publicadas (ignoradas).")
    print(f"Grupo A (publicadas so apos o fallback): {int((p['grupo'] == 'A').sum())} no total, {na} na amostra, {len(extra)} acrescentadas ao fim do CSV para rotular.")
    print(f"Grupo B: {int((p['grupo'] == 'B').sum())} no total, {len(ok) - na} na amostra.")


def calcular(verbose=True):
    arv = Arvore()
    rot = pd.read_csv(ROTULOS, dtype=str).fillna("")
    grp = pd.read_csv(GRUPOS, dtype=str)
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")[["id", "decisao", "tema_central_id"]]
    df = rot.merge(grp, on="id").merge(pub, on="id")
    faltam = int((df["tema_correto_id"] == "").sum())
    if faltam:
        print(f"ATENCAO: {faltam} questoes ainda sem rotulo (ignoradas).")
    df = df[df["tema_correto_id"] != ""].copy()
    nao_pub = int((df["decisao"] != "publicar").sum())
    if nao_pub:
        print(f"ATENCAO: {nao_pub} questoes da amostra nao estao mais publicadas (regras mudaram?).")
    df["certo"] = [
        r.decisao == "publicar" and r.tema_correto_id != "fora" and arv.relacionado(r.tema_central_id, r.tema_correto_id)
        for r in df.itertuples()
    ]
    df["certo_pior"] = df["certo"] & (df["incerto"] != "1")
    tot = publicadas()["grupo"].value_counts().to_dict()
    res = {}
    for cenario in ("certo", "certo_pior"):
        soma, lo_s, hi_s, N = 0.0, 0.0, 0.0, 0
        for g in ("A", "B"):
            x = df[df["grupo"] == g]
            n, k, Ng = len(x), int(x[cenario].sum()), tot.get(g, 0)
            if n == 0:
                continue
            p = k / n
            lo, hi = (p, p) if n >= Ng else wilson(k, n)
            soma += Ng * p
            lo_s += Ng * lo
            hi_s += Ng * hi
            N += Ng
            if verbose and cenario == "certo":
                print(f"grupo {g}: {k}/{n} certas ({p:.2f}) de {Ng} publicadas" + (" [censo]" if n >= Ng else f" IC95% {lo:.2f}-{hi:.2f}"))
        res[cenario] = (soma / N, lo_s / N, min(1.0, hi_s / N))
    if verbose:
        e, lo, hi = res["certo"]
        print(f"\nPRECISAO TOTAL estimada: {e:.3f} (IC aprox. {lo:.3f}-{hi:.3f})")
        print(f"Se todas as 'incertas' fossem erro: {res['certo_pior'][0]:.3f} (IC aprox. {res['certo_pior'][1]:.3f}-{res['certo_pior'][2]:.3f})")
        print(f"Questoes marcadas incertas (1): {(df['incerto'] == '1').sum()}")
        print("Erros:")
        print(df[~df["certo"]][["id", "grupo", "tema_central_id", "tema_correto_id"]].to_string(index=False))
    return res, len(df)


def previsao():
    res, n = calcular(verbose=False)
    e, lo, hi = res["certo"]
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str)
    cob = (pub["decisao"] == "publicar").mean()
    prev = round((e + res["certo_pior"][1]) / 2, 2)
    txt = (
        f"precisao_prevista: {prev:.2f}\n"
        f"precisao_intervalo: {res['certo_pior'][1]:.2f}-{min(hi, 1):.2f}\n"
        f"cobertura_prevista: {cob:.2f}\n"
        f"cobertura_intervalo: {cob:.2f}-{cob:.2f}\n\n"
        "RASCUNHO: reescreva com as suas palavras.\n"
        f"Rotulei {n} das publicadas as cegas. Grupo A (publicadas so apos o fallback com a arvore inteira) foi rotulado por inteiro; "
        "grupo B foi amostra aleatoria. A precisao total e a media ponderada pelos tamanhos dos grupos.\n"
        "Intervalo: Wilson a 95% no grupo B, combinado por pesos (aproximado). O limite inferior supoe que todas as questoes "
        "marcadas incertas estao erradas. A previsao fica entre a estimativa e esse limite, por cautela.\n"
        "A cobertura e exata nas 359 questoes; o risco esta na precisao.\n"
        "Limitacoes: amostra pequena; rotulos meus, sem formacao juridica especializada; a convencao dos temas duplicados nao foi confirmada.\n"
    )
    (ROOT / "previsao.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"sample": sample, "completar": completar, "evaluate": calcular, "previsao": previsao}.get(cmd, lambda: print(__doc__))()