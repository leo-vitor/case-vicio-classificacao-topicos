"""A/B do juiz: a expansao por IRMAOS melhora ou piora a decisao?

NAO executa por padrao (dry-run apenas conta chamadas e estima custo — GRATIS).
O `--rodar` chama o juiz real (GASTA API) e invalida parte do cache, porque muda o
prompt (lista de candidatos) de cada questao.

Compara, nas 93 rotuladas, o MESMO juiz (JUDGE_MODELS x RUNS_PER_MODEL) e as MESMAS
regras (src.decide), tres configuracoes de recuperacao:

  tfidf+filho       config atual (entrega)
  tfidf+top+dic     dicionario, lista pequena
  tfidf+irmao+dic   irmaos + dicionario (melhor recall)

Para cada config mede:
  - publicar / revisar / fora                (cobertura)
  - concordancia com a referencia nas publicadas (rotulos assistidos por IA)
  - escolha de GEMEO  (tema final com mesmo titulo da referencia, raiz diferente)
  - quantas foram a revisar pela regra de gemeos do src.decide
  - custo (tokens de entrada)

  .venv/bin/python -m src.experimentos.ab_juiz --dry-run      # conta chamadas novas, estima custo
  .venv/bin/python -m src.experimentos.ab_juiz --rodar        # executa (GASTA API)
  .venv/bin/python -m src.experimentos.ab_juiz --rodar --configs tfidf+filho tfidf+top+dic
  .venv/bin/python -m src.experimentos.ab_juiz --dry-run --rotulos data/rotulos_opus.tsv

Saidas em outputs/experimentos/ab_juiz/:
  plano.json                  (dry-run) chamadas novas/cache e tokens por config
  <config>.votos.jsonl        (rodar)  votos do juiz
  <config>.decisoes.csv       (rodar)  decisao por questao (com flags de gemeo)
  metricas.json               (rodar)  agregado por config
"""
import argparse
import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from src import judge as J
from src.config import JUDGE_BACKEND, JUDGE_MODELS, JUDGE_WORKERS, OUT, RUNS_PER_MODEL, TEMPERATURE
from src.decide import agregar, decidir
from src.dicionario import Dicionario
from src.eval import carregar_conjunto
from src.experimentos.experimento_irmaos import CHARS_POR_TOKEN, construir
from src.recuperacao import pool_publicavel, textos_temas
from src.temas import Arvore

EXP = OUT / "experimentos" / "ab_juiz"
MAPA = {"Direito Penal": "Penal", "Direito Processual Penal": "Processo Penal"}
CONFIGS_PADRAO = ["tfidf+filho", "tfidf+top+dic", "tfidf+irmao+dic"]


def _temp():
    return 0.0 if RUNS_PER_MODEL == 1 else TEMPERATURE


def _key_prefix(prompt, model, run):
    return hashlib.sha256(f"{JUDGE_BACKEND}|{model}|{_temp()}|{run}|{prompt}".encode()).hexdigest()


def plano(arv, q, ids, cands):
    """Conta chamadas novas (fora do cache) e tokens de entrada estimados."""
    novas, cache, tok = 0, 0, 0.0
    for i in ids:
        p = J.montar_prompt(arv, q.loc[i], cands[i])
        tok += len(p) * CHARS_POR_TOKEN
        for m in JUDGE_MODELS:
            for r in range(RUNS_PER_MODEL):
                if (J.JCACHE / f"{_key_prefix(p, m, r)}.json").exists():
                    cache += 1
                else:
                    novas += 1
    return {"questoes": len(ids), "chamadas_novas": novas, "cache": cache,
            "chamadas_total": novas + cache, "tokens_in_novos": round(tok, 0)}


def julgar(arv, q, ids, cands):
    """Roda o juiz (4 votos) para as questoes; devolve votos por id."""
    def tarefa(i):
        cid = cands[i]
        votos = [J.uma_chamada(arv, q.loc[i], cid, m, r)
                 for m in JUDGE_MODELS for r in range(RUNS_PER_MODEL)]
        return {"id": i, "votes": votos}

    with ThreadPoolExecutor(max_workers=JUDGE_WORKERS) as ex:
        return list(ex.map(tarefa, ids))


def metricas(arv, ids, rotmap, votos_por_id, cands, origem):
    gem = arv.gemeos()
    linhas = []
    for i in ids:
        votos = votos_por_id[i]
        fb = cands[i][0]
        ag = agregar(arv, votos, fb)
        dec, motivo = decidir(arv, ag)
        if dec == "publicar" and ag["tema"] in gem:
            if arv.raiz(ag["tema"]) != MAPA.get(origem.get(i, ""), origem.get(i, "")):
                dec, motivo = "revisar", "tema duplicado entre disciplinas"
        ref = rotmap[i]
        tema = ag["tema"]
        eh_gemeo = bool(tema) and arv.titulo.get(tema) == arv.titulo.get(ref) and (
            arv.raiz(tema) != arv.raiz(ref)
        )
        linhas.append({
            "id": i, "decisao": dec, "tema": tema or "", "referencia": ref,
            "correto_pela_regua": bool(tema) and arv.relacionado(tema, ref),
            "escolha_de_gemeo": eh_gemeo,
            "gemeo_no_motivo": "tema duplicado" in (motivo or ""),
            "fora": any(v["fora"] for v in votos),
        })
    df = pd.DataFrame(linhas)
    pub = df[df.decisao == "publicar"]
    cont = Counter(df.decisao)
    return df, {
        "n": len(df),
        "publicar": cont.get("publicar", 0),
        "revisar": cont.get("revisar", 0),
        "fora": cont.get("fora", 0),
        "cobertura": round(cont.get("publicar", 0) / len(df), 3),
        "concordancia_publicadas": round(pub.correto_pela_regua.mean(), 4) if len(pub) else None,
        "escolhas_de_gemeo": int(df.escolha_de_gemeo.sum()),
        "rebaixados_por_gemeo": int(df.gemeo_no_motivo.sum()),
    }


def main():
    ap = argparse.ArgumentParser(description="A/B do juiz entre configuracoes de recuperacao.")
    ap.add_argument("--rodar", action="store_true", help="executa o juiz (GASTA API); default: dry-run")
    ap.add_argument("--dry-run", action="store_true", help="so conta chamadas e estima custo (padrao)")
    ap.add_argument("--configs", nargs="*", default=CONFIGS_PADRAO)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--conjunto", default="todos")
    ap.add_argument("--rotulos", default=None, help="arquivo de rotulos alternativo (ex.: data/rotulos_opus.tsv)")
    args = ap.parse_args()

    arv = Arvore()
    q, ids, rotmap = carregar_conjunto(arv, args.conjunto, args.rotulos)
    tag = "_" + Path(args.rotulos).stem if args.rotulos else ""
    dic = Dicionario()
    pool = pool_publicavel(arv)
    t_texts = textos_temas(arv, pool)
    origem = q.set_index("id")["disciplina_origem"].to_dict()
    atual = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))

    EXP.mkdir(parents=True, exist_ok=True)
    saida = {"conjunto": args.conjunto, "k": args.k, "rotulos": args.rotulos,
             "juiz": JUDGE_MODELS, "rodadas_por_modelo": RUNS_PER_MODEL, "configs": {}}

    for cfg in args.configs:
        if cfg == "atual":
            # Braco de referencia: o candidatos.json da ENTREGA (inclui fallback/expandir_fora).
            # Custa 0 (100% do cache). Serve de ancora, NAO de par limpo (tem drift/fallback).
            cands = {i: atual[i]["candidatos"] for i in ids}
        else:
            cands = construir(arv, pool, t_texts, q, ids, dic, cfg, args.k)
        if not args.rodar:
            p = plano(arv, q, ids, cands)
            saida["configs"][cfg] = p
            print(f"{cfg:20s} novas={p['chamadas_novas']:5d} cache={p['cache']:5d} "
                  f"total={p['chamadas_total']:5d} tok_novos~{p['tokens_in_novos']:,.0f}")
            continue
        votos = julgar(arv, q, ids, cands)
        with open(EXP / f"{cfg}{tag}.votos.jsonl", "w", encoding="utf-8") as f:
            for r in votos:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        vp = {r["id"]: r["votes"] for r in votos}
        df, m = metricas(arv, ids, rotmap, vp, cands, origem)
        df.to_csv(EXP / f"{cfg}{tag}.decisoes.csv", index=False)
        saida["configs"][cfg] = m
        print(f"{cfg:20s} {m}")

    if args.rodar:
        arq = EXP / f"metricas{tag}.json"
        if arq.exists():  # acumula entre execucoes parciais (ex.: creditos acabarem no meio)
            try:
                anterior = json.loads(arq.read_text(encoding="utf-8"))
                saida["configs"] = {**anterior.get("configs", {}), **saida["configs"]}
            except Exception:
                pass
        arq.write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"escrito: {arq}")
        print("STATS do juiz:", J.STATS)
        from src import uso
        uso.registrar("ab_juiz", J.STATS, extra={"rotulos": str(args.rotulos), "configs": args.configs})
    else:
        (EXP / f"plano{tag}.json").write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
        novas = sum(v["chamadas_novas"] for v in saida["configs"].values())
        print(f"\nTOTAL chamadas novas: {novas} (dry-run nao gasta nada)")
        print(f"escrito: {EXP}/plano{tag}.json")


if __name__ == "__main__":
    main()
