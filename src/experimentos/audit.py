"""Auditoria metodologica (sem chamadas de API).

  python -m src.experimentos.audit recall     recall dos candidatos usando a amostra rotulada
  python -m src.experimentos.audit erros      decompoe os erros publicados (retrieval x decisao)
  python -m src.experimentos.audit votos      modelo latente (Dawid-Skene) usando os 4 votos
  python -m src.experimentos.audit template   cria outputs/rotuladores.csv para varios anotadores
  python -m src.experimentos.audit latente    roda Dawid-Skene sobre outputs/rotuladores.csv

Por que existe: um unico modelo rotulador nao e gabarito. A precisao obtida
comparando o rotulador com o juiz mede concordancia entre LLMs, nao verdade.
Aqui a gente separa erro de retrieval de erro de decisao, e estima a confianca
de cada anotador sem depender de rotulos de especialistas (modelo de classes
latentes, Dawid & Skene 1979, via EM).

Entradas:
  outputs/amostra_rotulagem.csv   amostra rotulada (id, tema_correto_id, incerto, fonte)
  outputs/candidatos.json         candidatos entregues aos juizes
  outputs/votos.jsonl             4 votos por questao
  publicacao.csv                  decisao atual
Saidas:
  outputs/auditoria_recall.csv
  outputs/auditoria_erros.csv
  outputs/latente_votos.csv
  outputs/rotuladores.csv         (template para varios anotadores)
  outputs/rotulos_latentes.csv    (consenso latente dos anotadores)
"""
import json
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from src.config import OUT, ROOT
from src.temas import Arvore

LABELS_FILE = OUT / "rotuladores.csv"
LATENTES = OUT / "rotulos_latentes.csv"


def _amostra():
    return pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")


def _publicacao():
    """Usa o snapshot congelado (antes da politica seletiva) para diagnosticar os
    erros do pipeline completo; senao os rebaixamentos esconderiam os erros."""
    base = OUT / "publicacao_congelada.csv"
    path = base if base.exists() else ROOT / "publicacao.csv"
    return pd.read_csv(path, dtype=str).fillna("").set_index("id")


def _candidatos():
    return json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))


def _votos():
    return {r["id"]: r["votes"] for r in (json.loads(l) for l in open(OUT / "votos.jsonl", encoding="utf-8"))}


def recall():
    """Quanto o tema correto (ou pai/filho) aparece entre os candidatos."""
    arv = Arvore()
    amostra = _amostra()
    cand = _candidatos()
    linhas = []
    for r in amostra.itertuples():
        if r.tema_correto_id == "" or r.tema_correto_id == "fora":
            continue
        ids = cand.get(r.id, {}).get("candidatos", [])
        presente = any(arv.relacionado(t, r.tema_correto_id) for t in ids)
        linhas.append(
            {
                "id": r.id,
                "tema_correto_id": r.tema_correto_id,
                "n_candidatos": len(ids),
                "arvore_inteira": len(ids) > 100,
                "recall": presente,
            }
        )
    df = pd.DataFrame(linhas)
    df.to_csv(OUT / "auditoria_recall.csv", index=False)
    print(f"Recall dos candidatos: {df['recall'].mean():.3f} ({int(df['recall'].sum())}/{len(df)})")
    print(df.groupby("arvore_inteira")["recall"].agg(["size", "mean"]).to_string())
    faltas = df[~df["recall"]]
    if len(faltas):
        print("Temas corretos que NAO foram oferecidos ao juiz:")
        print(faltas[["id", "tema_correto_id", "n_candidatos"]].to_string(index=False))
    return df


def erros():
    """Separa os erros publicados entre falha de retrieval e falha de decisao."""
    arv = Arvore()
    amostra = _amostra()
    pub = _publicacao()
    cand = _candidatos()
    linhas = []
    for r in amostra.itertuples():
        if r.tema_correto_id in ("", "fora"):
            continue
        if pub.loc[r.id, "decisao"] != "publicar":
            continue
        tema = pub.loc[r.id, "tema_central_id"]
        certo = arv.relacionado(tema, r.tema_correto_id)
        if certo:
            continue
        ids = cand.get(r.id, {}).get("candidatos", [])
        offered = any(arv.relacionado(t, r.tema_correto_id) for t in ids)
        linhas.append(
            {
                "id": r.id,
                "tema_modelo": tema,
                "caminho_modelo": arv.caminho.get(tema, ""),
                "tema_rotulo": r.tema_correto_id,
                "caminho_rotulo": arv.caminho.get(r.tema_correto_id, ""),
                "rotulo_oferecido_ao_juiz": offered,
                "causa_provavel": "retrieval" if not offered else "decisao",
                "incerto": r.incerto,
                "fonte": getattr(r, "fonte", ""),
            }
        )
    df = pd.DataFrame(linhas)
    df.to_csv(OUT / "auditoria_erros.csv", index=False)
    if len(df):
        print("Erros publicados por causa provavel:")
        print(df["causa_provavel"].value_counts().to_string())
        print(df[["id", "tema_modelo", "tema_rotulo", "causa_provavel"]].to_string(index=False))
    else:
        print("Nenhum erro publicado encontrado na amostra rotulada.")
    return df


def template():
    """Cria o arquivo de anotadores a partir da amostra atual. Preencha as colunas
    extras com modelos de familias diferentes (ex.: claude, gpt, qwen, llama local).
    Use 'fora' quando nenhum tema servir e deixe vazio quando nao anotou."""
    amostra = _amostra()
    base = pd.DataFrame({"id": amostra["id"]})
    base["modelo_atual"] = amostra["tema_correto_id"]
    for c in ("anotador_2", "anotador_3", "anotador_4"):
        base[c] = ""
    base.to_csv(LABELS_FILE, index=False)
    print(f"Template em {LABELS_FILE}: {len(base)} linhas. Preencha anotador_2..4.")
    return base


def _ds_em(obs, labelers, labels, iters=100, alpha=1.0):
    """Modelo latente 'one-coin' via EM, robusto quando o espaco de rotulos e
    grande e poucos anotadores olham cada item.

    Ideia: cada anotador j acerta o rotulo verdadeiro com probabilidade acc_j.
    Quando erra, distribui a massa uniformemente entre os OUTROS rotulos
    observados para aquele item. O posterior sobre o rotulo verdadeiro e
    calculado sobre a uniao dos rotulos observados no item (nao sobre os 377).
    Estima acc_j sem nenhum rotulo de especialista.

    Referencia: Dawid & Skene (1979), caso particular one-coin (Raykar et al., 2010).
    """
    # candidatos por item = uniao dos rotulos observados
    cands = []
    for o in obs:
        c = sorted(set(o.values()))
        cands.append(c if c else labels[:1])
    acc = {j: 0.7 for j in labelers}
    Q = []
    for _ in range(iters):
        Q = []
        for o, c in zip(obs, cands):
            m = len(c)
            posts = {}
            for lab in c:
                p = 1.0
                for j, y in o.items():
                    if m == 1:
                        p *= 1.0
                    elif y == lab:
                        p *= acc[j]
                    else:
                        p *= (1 - acc[j]) / (m - 1)
                posts[lab] = p
            s = sum(posts.values()) or 1.0
            Q.append({lab: p / s for lab, p in posts.items()})
        for j in labelers:
            num = den = alpha
            for o, q in zip(obs, Q):
                if j not in o:
                    continue
                den += 1.0
                for lab, p in q.items():
                    if o[j] == lab:
                        num += p
            acc[j] = min(0.999, max(0.5, num / den))
    return None, acc, Q


def _roda_latente(df, colunas, saida, rotulo_col="id"):
    labels = sorted({v for c in colunas for v in df[c].tolist() if v != ""})
    obs = []
    for _, row in df.iterrows():
        o = {c: row[c] for c in colunas if row[c] != ""}
        if o:
            obs.append(o)
        else:
            obs.append({})
    labelers = colunas
    _, acc, Q = _ds_em(obs, labelers, labels)
    linhas = []
    for (_, row), o, q in zip(df.iterrows(), obs, Q):
        if not q:
            linhas.append({"id": row[rotulo_col], "latente": "", "prob": 0.0, "n_anotadores": 0})
            continue
        best, prob = max(q.items(), key=lambda kv: kv[1])
        linhas.append({"id": row[rotulo_col], "latente": best, "prob": round(prob, 4), "n_anotadores": len(o)})
    out = pd.DataFrame(linhas)
    out.to_csv(saida, index=False)
    print(f"Latente (one-coin): {len(out)} itens -> {saida}")
    print("Acuracia estimada por anotador (sem gabarito):")
    for j, a in acc.items():
        print(f"  {j}: {a:.3f}")
    return out, acc


def votos():
    """Modelo latente usando os 4 votos dos juizes como anotadores.
    Cuidado: os votos sao correlacionados e limitados aos candidatos. Serve como
    sinal auxiliar de incerteza, nao como verdade."""
    arv = Arvore()
    vs = _votos()
    linhas = []
    for qid, votos_ in vs.items():
        row = {"id": qid}
        for i, v in enumerate(votos_):
            if v.get("fora"):
                row[f"v{i}"] = "fora"
            elif v.get("tema_id"):
                row[f"v{i}"] = v["tema_id"]
            else:
                row[f"v{i}"] = "resposta_invalida"
        linhas.append(row)
    df = pd.DataFrame(linhas).fillna("")
    out, acc = _roda_latente(df, [c for c in df.columns if c.startswith("v")], OUT / "latente_votos.csv")
    return out, acc


def latente():
    if not LABELS_FILE.exists():
        print(f"Nao existe {LABELS_FILE}. Rode 'python -m src.experimentos.audit template' e preencha.")
        return
    df = pd.read_csv(LABELS_FILE, dtype=str).fillna("")
    cols = [c for c in df.columns if c != "id"]
    out, acc = _roda_latente(df, cols, LATENTES)
    return out, acc


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"recall": recall, "erros": erros, "template": template, "latente": latente, "votos": votos}.get(
        cmd, lambda: print(__doc__)
    )()
