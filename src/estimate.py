"""Etapa 5: estimar a precisao das publicadas sem gabarito.

  python -m src.estimate sample     amostra estratificada para rotular as cegas
  python -m src.estimate completar  aproveita a amostra ja rotulada, cria os grupos
                                     e acrescenta o grupo A que faltar (linhas em branco)
  python -m src.estimate evaluate   precisao (so publicadas) e cobertura (diagnostico)
  python -m src.estimate previsao   escreve previsao.txt

Conceitos importantes (alinhados ao LEIA-ME do case):
  - A precisao e medida SOMENTE sobre as questoes publicadas.
  - As questoes da amostra que hoje estao em revisar/fora sao diagnosticos de
    cobertura/recall, NAO entram no denominador da precisao.
  - Grupos de publicadas:
      A = publicadas so depois do fallback com a arvore inteira (maior risco): censo.
      B = demais publicadas: amostra.
  - O arquivo outputs/amostra_grupos.csv guarda o grupo de cada questao (nao abrir
    enquanto se rotula, para nao contaminar).
  - A coluna 'fonte' registra a origem do rotulo (ex.: eu, ds, misto).

Metrica de acerto (regua do case): mesmo no, pai ou filho direto.
Irmãos sob o mesmo tema pai contam como erro.
"""
import json
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
SELETIVA = OUT / "seletiva_resumo.json"


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def _publicacao():
    return pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")


def publicadas():
    pub = _publicacao()
    p = pub[pub["decisao"] == "publicar"].copy()
    if ANTES.exists():
        antes = pd.read_csv(ANTES, dtype=str).fillna("").set_index("id")
        p["grupo"] = ["A" if antes.loc[i, "decisao"] != "publicar" else "B" for i in p["id"]]
    else:
        p["grupo"] = "B"
    return p


def _texto(q, i, lim=1800):
    return q.loc[i, "texto"][:lim]


def sample():
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")
    p = publicadas()
    a = p[p["grupo"] == "A"]
    b = p[p["grupo"] == "B"].sample(max(0, N_AMOSTRA - len(a)), random_state=SEED)
    s = pd.concat([a, b]).sample(frac=1, random_state=SEED)
    pd.DataFrame(
        {
            "id": s["id"].values,
            "parte": "",
            "texto": [_texto(q, i) for i in s["id"]],
            "tema_correto_id": "",
            "incerto": "",
            "fonte": "",
        }
    ).to_csv(ROTULOS, index=False)
    s[["id", "grupo"]].to_csv(GRUPOS, index=False)
    arv = Arvore()
    arv.ativos[arv.ativos.nivel >= 1][["tema_id", "caminho"]].to_csv(OUT / "temas_referencia.csv", index=False)
    print(f"Amostra de {len(s)} em {ROTULOS}: grupo A inteiro ({len(a)}) + {len(s) - len(a)} do grupo B.")
    print("Preencha tema_correto_id ('fora' se nenhum serve; incerto=1 se tiver duvida).")
    print("Nao abra publicacao.csv nem amostra_grupos.csv enquanto rotula.")


def _garantir_colunas(df, cols=("parte", "incerto", "fonte")):
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df


def _textos(g, ids, lim=1800):
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id")
    return [q.loc[i, "texto"][:lim] for i in ids]


def completar():
    """Aproveita a amostra atual. Cria/atualiza outputs/amostra_grupos.csv para as
    publicadas atuais e acrescenta, ao fim, as publicadas do grupo A que faltam
    rotular (linhas em branco). Preserva colunas extras (parte, fonte etc.)."""
    rot = pd.read_csv(ROTULOS, dtype=str).fillna("")
    rot = _garantir_colunas(rot)
    p = publicadas()
    g = p.set_index("id")["grupo"]
    ja = set(rot["id"])
    novos = p[(p["grupo"] == "A") & ~p["id"].isin(ja)]
    if len(novos):
        extra = pd.DataFrame(
            {
                "id": novos["id"].values,
                "parte": "",
                "texto": _textos(None, novos["id"].values),
                "tema_correto_id": "",
                "incerto": "",
                "fonte": "",
            }
        )
        rot = pd.concat([rot, extra], ignore_index=True).fillna("")
    rot.to_csv(ROTULOS, index=False)
    ok = rot[rot["id"].isin(g.index)]
    pd.DataFrame({"id": ok["id"].values, "grupo": [g[i] for i in ok["id"]]}).to_csv(GRUPOS, index=False)
    na = int((g[ok["id"]] == "A").sum())
    fora = int((~rot["id"].isin(g.index)).sum())
    print(f"Amostra: {len(rot)} linhas ({fora} fora das publicadas atuais, ignoradas na precisao).")
    print(f"Grupo A (publicadas so apos o fallback): {int((p['grupo'] == 'A').sum())} no total, "
          f"{na} na amostra, {len(novos)} acrescentadas ao fim para rotular.")
    print(f"Grupo B: {int((p['grupo'] == 'B').sum())} no total, {len(ok) - na} na amostra.")
    if len(novos):
        print("Pendentes de rotulo (grupo A):", ", ".join(sorted(novos["id"])))


def _amostra_publicada(arv):
    """Retorna apenas as linhas da amostra que hoje estao publicadas, com o campo certo."""
    rot = _garantir_colunas(pd.read_csv(ROTULOS, dtype=str).fillna(""))
    grp = pd.read_csv(GRUPOS, dtype=str).fillna("")
    pub = _publicacao()[["id", "decisao", "tema_central_id", "extras_ids", "confianca"]]
    df = rot.merge(grp, on="id", how="left").merge(pub, on="id", how="left")
    rotuladas = df["tema_correto_id"] != ""
    pub_df = df[rotuladas & (df["decisao"] == "publicar")].copy()
    pub_df["certo"] = [
        r.tema_correto_id != "fora" and arv.relacionado(r.tema_central_id, r.tema_correto_id)
        for r in pub_df.itertuples()
    ]
    pub_df["certo_estrito"] = [
        r.tema_correto_id != "fora" and r.tema_central_id == r.tema_correto_id
        for r in pub_df.itertuples()
    ]
    pub_df["certo_pior"] = pub_df["certo"] & (pub_df["incerto"] != "1")
    return df, pub_df


def _diagnostico_cobertura(arv, df):
    """Questoes rotuladas que NAO estao publicadas hoje: sao erro de cobertura/recall,
    nao de precisao."""
    x = df[(df["tema_correto_id"] != "") & (df["decisao"].isin(["revisar", "fora"]))].copy()
    if len(x) == 0:
        return x
    x["label_valido"] = x["tema_correto_id"] != "fora"
    x["sugestao_relacionada"] = [
        bool(r.label_valido) and arv.relacionado(r.tema_central_id, r.tema_correto_id)
        for r in x.itertuples()
    ]
    x.to_csv(OUT / "cobertura_diagnostico.csv", index=False)
    return x


def calcular(verbose=True):
    arv = Arvore()
    df, pubdf = _amostra_publicada(arv)
    diag = _diagnostico_cobertura(arv, df)
    rotuladas = int((df["tema_correto_id"] != "").sum())
    faltam = int((df["tema_correto_id"] == "").sum())
    if verbose:
        print(f"Amostra rotulada: {rotuladas} linhas; {faltam} sem rotulo (ignoradas).")
        if len(diag):
            print(f"Diagnostico: {len(diag)} rotuladas hoje em revisar/fora "
                  f"(cobertura, fora do denominador de precisao) -> {OUT / 'cobertura_diagnostico.csv'}")
    tot = publicadas()["grupo"].value_counts().to_dict()
    res = {}
    for cenario in ("certo", "certo_estrito", "certo_pior"):
        soma, lo_s, hi_s, N = 0.0, 0.0, 0.0, 0
        for g in ("A", "B"):
            x = pubdf[pubdf["grupo"] == g]
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
                tag = " [censo]" if n >= Ng else f" IC95% {lo:.2f}-{hi:.2f}"
                print(f"grupo {g}: {k}/{n} publicadas certas ({p:.2f}) de {Ng}{tag}")
        res[cenario] = (soma / N if N else 0.0, lo_s / N if N else 0.0, min(1.0, hi_s / N if N else 0.0))
    if verbose:
        e, lo, hi = res["certo"]
        print(f"\nPRECISAO (regua pai/filho): {e:.3f} (IC aprox. {lo:.3f}-{hi:.3f})")
        print(f"PRECISAO estrita (mesmo id): {res['certo_estrito'][0]:.3f} (IC aprox. {res['certo_estrito'][1]:.3f}-{res['certo_estrito'][2]:.3f})")
        print(f"Cenario pessimista (toda 'incerto'=erro): {res['certo_pior'][0]:.3f} (IC aprox. {res['certo_pior'][1]:.3f}-{res['certo_pior'][2]:.3f})")
        print(f"Questoes marcadas incertas (1): {(pubdf['incerto'] == '1').sum()}")
        if "fonte" in pubdf.columns:
            print("Por fonte:", pubdf["fonte"].replace("", "nao_informado").value_counts().to_dict())
        print("Erros publicados (rotulo x tema do modelo):")
        cols = ["id", "grupo", "tema_central_id", "tema_correto_id", "incerto", "fonte"]
        cols = [c for c in cols if c in pubdf.columns]
        print(pubdf[~pubdf["certo"]][cols].to_string(index=False))
    return res, len(pubdf)


def _cobertura():
    pub = _publicacao()
    cob = (pub["decisao"] == "publicar").mean()
    return cob, len(pub), int((pub["decisao"] == "publicar").sum())


def _seletiva():
    if SELETIVA.exists():
        try:
            return json.loads(SELETIVA.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cobertura_intervalo(cob, n_pub):
    """Intervalo de cobertura. So usa o bootstrap da camada seletiva quando o
    publicacao.csv atual E o resultado seletivo (mesmo numero de publicadas).
    Caso contrario a cobertura e a contagem deterministica."""
    d = _seletiva()
    if d and int(d.get("n_publicadas_seletiva", -1)) == n_pub:
        return float(d.get("cobertura_lo", cob)), float(d.get("cobertura_hi", cob)), d.get("metodo_cobertura", "")
    return cob, cob, ""


def previsao():
    res, n = calcular(verbose=False)
    e, lo, hi = res["certo"]
    e_pior, lo_pior, _ = res["certo_pior"]
    cob, total, n_pub = _cobertura()
    cob_lo, cob_hi, metodo_cob = _cobertura_intervalo(cob, n_pub)
    # Previsao conservadora: media entre a estimativa pontual e o limite inferior
    # do cenario pessimista (incertas contam como erro). Nunca acima da estimativa.
    prev = round(min(e, (e + lo_pior) / 2), 2)
    prev_lo = round(min(lo_pior, lo), 2)
    prev_hi = round(min(hi, 0.999), 2)
    sel = _seletiva()
    alt = ""
    if sel and int(sel.get("n_publicadas_seletiva", -1)) != n_pub:
        alt = (
            f"\n5) Existe uma politica seletiva calibrada alternativa (limiar {sel.get('threshold')}, "
            f"regra '{sel.get('regra')}') que publicaria {sel.get('n_publicadas_seletiva')} questoes "
            f"(cobertura {sel.get('cobertura')}); ela ainda nao foi aplicada ao publicacao.csv.\n"
        )
    elif sel and metodo_cob:
        alt = (
            f"\n5) Politica seletiva ativa (regra '{sel.get('regra')}', limiar {sel.get('threshold')}): "
            f"calibracao com {sel.get('cal_n')} itens (precisao {sel.get('cal_prec')}) e "
            f"validacao com {sel.get('val_n')} itens (precisao {sel.get('val_prec')}). "
            "O numero de precisao acima usa a amostra inteira e e descritivo; a estimativa sem vies "
            "de ajuste do limiar e a da validacao.\n"
        )
    sele_ativo = "Sim" if metodo_cob else "Nao"
    txt = (
        f"precisao_prevista: {prev:.2f}\n"
        f"precisao_intervalo: {prev_lo:.2f}-{prev_hi:.2f}\n"
        f"cobertura_prevista: {cob:.2f}\n"
        f"cobertura_intervalo: {cob_lo:.2f}-{cob_hi:.2f}\n\n"
        f"publicadas: {n_pub} de {total}\n"
        f"politica_seletiva_aplicada: {sele_ativo}\n\n"
        "Como calculei.\n"
        f"1) Precisao: usei {n} questoes publicadas rotuladas. Um acerto e publicar no tema "
        "atribuido ou em um no pai/filho direto (regua do case); irmaos contam como erro. "
        "A estimativa e a media ponderada pelos tamanhos dos grupos A (publicadas so apos o fallback, "
        "rotulado por inteiro quando possivel) e B (amostra).\n"
        "2) Intervalo de precisao: Wilson 95% por grupo, combinado por pesos (aproximado). O limite "
        "inferior tambem considera o cenario em que toda questao marcada como incerta esta errada.\n"
        "3) Previsao: ponto entre a estimativa e o limite inferior do cenario pessimista, por cautela.\n"
        "4) Cobertura: fracao de publicadas nas 359. "
        + (f"Intervalo por {metodo_cob}; " if metodo_cob else "A cobertura e a contagem deterministica do pipeline (sem amostragem); ")
        + "o risco desta entrega esta na precisao, nao na contagem.\n"
        + alt
        + "\nLimitacoes.\n"
        "- Amostra pequena e rotulada com assistencia de IA (registrar quais ferramentas em docs/transparencia_rotulos.md). "
        "A precisao medida e concordancia com um rotulador, nao com os especialistas do case; pode ser otimista "
        "por correlacao entre modelos.\n"
        "- Nao ha gabarito dos especialistas. A avaliacao usa uma amostra propria e a regua pai/filho.\n"
        "- A convencao para os temas com titulo duplicado (gemeos) nao foi confirmada pela organizacao; "
        "os casos ambiguos foram mantidos em revisao.\n"
        "- O intervalo de cobertura da politica seletiva (quando aplicada) vem do bootstrap do conjunto "
        "de calibracao re-escolhendo o limiar; e largo porque o conjunto rotulado e pequeno.\n"
    )
    # NAO sobrescreve o previsao.txt da entrega (escrito a mao): grava ao lado.
    (ROOT / "previsao_automatica.txt").write_text(txt, encoding="utf-8")
    print("(gravado em previsao_automatica.txt; o previsao.txt da entrega nao foi tocado)\n")
    print(txt)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"sample": sample, "completar": completar, "evaluate": calcular, "previsao": previsao}.get(cmd, lambda: print(__doc__))()
