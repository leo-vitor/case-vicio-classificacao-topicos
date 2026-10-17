"""Fase 0/1: avaliacao canonica de recuperacao (offline, sem API).

Um unico ponto de entrada para comparar configuracoes de recuperacao com as MESMAS
definicoes e o MESMO conjunto de avaliacao. Registra configuracao, metricas, IDs dos
erros e versao dos dados, para que os numeros sejam reproduziveis e comparaveis.

Metricas (regua do case; irmao NAO conta), com denominador explicito:
  - recall_exato : tema_correto_id presente na lista de candidatos.
  - recall_hier  : tema, pai ou filho direto presente (o que basta para o juiz acertar).
  - recall_via_pai: o tema so entrou porque o pai foi recuperado (subset de recall_hier).

Uso (na raiz, com o .venv):
  python -m src.eval --split                 # cria dev/holdout estratificado
  python -m src.eval --config tfidf+filho --k 10
  python -m src.eval --config tfidf+irmao+dic --conjunto holdout
  python -m src.eval --sweep                 # bateria principal (k=10)
  python -m src.eval --sweep --rotulos data/rotulos_opus.tsv   # rotulagem alternativa

Saidas:
  outputs/avaliacao/registro.csv             # uma linha por execucao (rotulos padrao)
  outputs/avaliacao/registro_<rotulos>.csv   # quando --rotulos (ex.: registro_rotulos_opus.csv)
  outputs/avaliacao/runs/<run_id>.json       # config + metricas + erros + versao dos dados
  outputs/avaliacao/split.csv                # dev/holdout (uma vez)

Nada disso altera o pipeline final (publicacao.csv permanece intacto).
"""
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DATA, OUT
from src.dicionario import Dicionario
from src.recuperacao import avaliar, montar_candidatos, pool_publicavel, ranking, texto_questao, textos_temas
from src.temas import Arvore

AVAL = OUT / "avaliacao"
RUNS = AVAL / "runs"
LEG = "Direito Penal - Legislação Especial"
SEED = 42
ROTULOS_PADRAO = OUT / "amostra_rotulagem.csv"


def _hash(path, n=12):
    p = DATA / path if not str(path).startswith("/") else path
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()[:n]
    except OSError:
        return "ausente"


def versao_dados(rotulos=None):
    return {
        "questoes_limpas": _hash(OUT / "questoes_limpas.csv"),
        "amostra_rotulagem": _hash(rotulos or ROTULOS_PADRAO),
        "temas": _hash(DATA / "temas.csv"),
        "dicionario": Dicionario().versao(),
    }


def carregar_rotulos(rotulos=None):
    """Le um arquivo de rotulos (CSV ou TSV). Aceita 'tema_correto_id' ou 'tema_id'.

    Devolve (dataframe, nome_da_coluna_de_tema). Nao altera o padrao (amostra_rotulagem).
    """
    p = Path(rotulos) if rotulos else ROTULOS_PADRAO
    if not p.is_absolute():
        p = p if p.exists() else DATA / p
    sep = "\t" if str(p).lower().endswith((".tsv", ".tab")) else ","
    df = pd.read_csv(p, sep=sep, dtype=str).fillna("")
    col = "tema_correto_id" if "tema_correto_id" in df.columns else "tema_id"
    df = df[df[col] != ""].copy()
    return df, col


def carregar_conjunto(arv, conjunto="todos", rotulos=None):
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    rdf, col = carregar_rotulos(rotulos)
    rotmap = dict(zip(rdf.id, rdf[col]))
    ids = [i for i in q.id if i in rotmap]
    if conjunto != "todos":
        sp = pd.read_csv(AVAL / "split.csv", dtype=str).set_index("id")
        ids = [i for i in ids if i in sp.index and sp.loc[i, "parte"] == conjunto]
    return q, ids, rotmap


def parse_config(cfg):
    partes = cfg.split("+")
    retriever = partes[0]
    dic = "dic" in partes[1:]
    modos = [p for p in partes[1:] if p != "dic"]
    modo = modos[0] if modos else "filho"
    return retriever, modo, dic


def rodar(config, k=10, conjunto="todos", arv=None, q=None, ids=None, rotmap=None, dic=None, rotulos=None):
    """Executa uma config e devolve o registro (com metricas e erros)."""
    arv = arv or Arvore()
    if q is None:
        q, ids, rotmap = carregar_conjunto(arv, conjunto, rotulos)
    dicionario = dic if dic is not None else Dicionario()
    retriever, modo, usa_dic = parse_config(config)

    pool = pool_publicavel(arv)
    t_texts = textos_temas(arv, pool)
    q_texts = [texto_questao(q.loc[i]) for i in ids]
    if usa_dic:
        q_texts = [dicionario.expandir(t) for t in q_texts]

    t0 = time.time()
    ranks, _ = ranking(retriever, q_texts, t_texts)
    cands = {qid: montar_candidatos(arv, pool, ranks[n], k, modo) for n, qid in enumerate(ids)}
    m = avaliar(arv, ids, cands, rotmap)
    seg = round(time.time() - t0, 2)

    sufixo = f"_{Path(rotulos).stem}" if rotulos else ""
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{config}_k{k}_{conjunto}{sufixo}"
    reg = {
        "run_id": run_id,
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config,
        "recuperador": retriever,
        "expansao": modo,
        "dicionario": usa_dic,
        "k": k,
        "conjunto": conjunto,
        "rotulos": str(rotulos) if rotulos else str(ROTULOS_PADRAO),
        "dados": versao_dados(rotulos),
        "segundos": seg,
        "metricas": {kk: m[kk] for kk in ("n", "recall_exato", "recall_hier", "recall_via_pai", "cands_media")},
        "legislacao_especial": m["por_disciplina"].get(LEG, {"n": 0, "acertos": 0, "recall": 0.0}),
        "por_disciplina": m["por_disciplina"],
        "erros_ids": m["erros"],
    }
    return reg


def salvar(reg, registro=None):
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{reg['run_id']}.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    linha = {
        "run_id": reg["run_id"], "criado_em": reg["criado_em"], "config": reg["config"],
        "k": reg["k"], "conjunto": reg["conjunto"], "n": reg["metricas"]["n"],
        "recall_exato": round(reg["metricas"]["recall_exato"], 4),
        "recall_hier": round(reg["metricas"]["recall_hier"], 4),
        "cands_media": round(reg["metricas"]["cands_media"], 1),
        "leg_esp_recall": round(reg["legislacao_especial"]["recall"], 4),
        "n_erros": len(reg["erros_ids"]),
        "dic_versao": reg["dados"]["dicionario"], "segundos": reg["segundos"],
        "dados_questoes": reg["dados"]["questoes_limpas"],
    }
    f = Path(registro) if registro else (AVAL / "registro.csv")
    df = pd.DataFrame([linha])
    df.to_csv(f, mode="a", header=not f.exists(), index=False)


def fazer_split(fracao_dev=0.66):
    """Split estratificado por disciplina, deterministico, reservando holdout para comparacao."""
    arv = Arvore()
    rot = pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")
    rot = rot[rot["tema_correto_id"] != ""][["id", "tema_correto_id"]].copy()
    rot["disciplina"] = rot["tema_correto_id"].map(lambda t: arv.raiz(t))
    rng = np.random.default_rng(SEED)
    rot = rot.assign(_r=rng.permutation(len(rot)))
    partes = []
    for _, g in rot.groupby("disciplina"):
        g = g.sort_values("_r")
        corte = max(1, round(len(g) * fracao_dev)) if len(g) > 1 else len(g)
        g = g.assign(parte=["dev"] * corte + ["holdout"] * (len(g) - corte))
        partes.append(g[["id", "disciplina", "parte"]])
    out = pd.concat(partes).sort_values("id")
    AVAL.mkdir(parents=True, exist_ok=True)
    out.to_csv(AVAL / "split.csv", index=False)
    print(f"split.csv: {len(out)} rotuladas | dev={(out.parte=='dev').sum()} holdout={(out.parte=='holdout').sum()}")
    print(out.groupby(["disciplina", "parte"]).size().to_string())


SWEEP = [
    "tfidf+top", "tfidf+pai", "tfidf+filho", "tfidf+irmao3", "tfidf+irmao",
    "tfidf+filho+dic", "tfidf+irmao+dic", "tfidf+top+dic",
    "bm25+filho", "bm25+irmao", "rrf+filho", "rrf+irmao",
]


def main():
    args = sys.argv[1:]
    arv = Arvore()

    if "--split" in args:
        fazer_split()
        return

    k = int(args[args.index("--k") + 1]) if "--k" in args else 10
    conjunto = args[args.index("--conjunto") + 1] if "--conjunto" in args else "todos"
    rotulos = args[args.index("--rotulos") + 1] if "--rotulos" in args else None
    registro = AVAL / f"registro_{Path(rotulos).stem}.csv" if rotulos else None

    if "--sweep" in args:
        q, ids, rotmap = carregar_conjunto(arv, conjunto, rotulos)
        dic = Dicionario()
        linhas = []
        for cfg in SWEEP:
            reg = rodar(cfg, k, conjunto, arv, q, ids, rotmap, dic, rotulos)
            salvar(reg, registro)
            linhas.append({
                "config": cfg, "n": reg["metricas"]["n"],
                "recall_exato": round(reg["metricas"]["recall_exato"], 3),
                "recall_hier": round(reg["metricas"]["recall_hier"], 3),
                "cands": round(reg["metricas"]["cands_media"], 1),
                "leg_esp": f"{reg['legislacao_especial']['acertos']}/{reg['legislacao_especial']['n']}",
            })
        print(f"\n=== sweep k={k} (conjunto={conjunto}) ===")
        print(pd.DataFrame(linhas).to_string(index=False))
        print(f"\nleg_esp = recall em {LEG}")
        return

    if "--config" in args:
        cfg = args[args.index("--config") + 1]
        reg = rodar(cfg, k, conjunto, arv, rotulos=rotulos)
        salvar(reg, registro)
        m = reg["metricas"]
        print(f"{cfg} k={k} [{conjunto}] n={m['n']}")
        print(f"  recall_exato={m['recall_exato']:.3f}  recall_hier={m['recall_hier']:.3f}  cands_media={m['cands_media']:.1f}")
        print(f"  {LEG}: {reg['legislacao_especial']['acertos']}/{reg['legislacao_especial']['n']} = {reg['legislacao_especial']['recall']:.2f}")
        print(f"  erros ({len(reg['erros_ids'])}): {', '.join(reg['erros_ids'])}")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
