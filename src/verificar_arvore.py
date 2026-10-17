"""Etapa 4b: verificacao com a arvore inteira (modelo barato, 1 voto por questao publicada).

Motivo: nos erros adjudicados, o tema certo nao estava entre os candidatos que o juiz recebeu.
Com a arvore inteira, o verificador enxerga todos os temas.

  python -m src.verificar_arvore            so conta as chamadas novas (dry-run, nao gasta nada)
  python -m src.verificar_arvore --rodar    executa e grava outputs/votos_verificacao.jsonl

Variavel CONTEXT_CACHE=1 envia o prefixo (instrucoes + arvore) via cache de contexto do
Gemini: o bloco de ~9 mil tokens e enviado UMA vez em vez de em toda chamada (ver
src.contexto_cache). Desligado por padrao; a chave do cache em disco nao muda.

Depois, o decide.py acrescenta esse voto aos votos de cada questao (ver patch no README).
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src import judge as J
from src.config import JUDGE_BACKEND, JUDGE_WORKERS, OUT, RUNS_PER_MODEL, TEMPERATURE
from src.temas import Arvore

MODELO = "gemini-3.1-flash-lite"


def main():
    rodar = "--rodar" in sys.argv
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    pub = pd.read_csv(OUT / "publicacao_congelada.csv", dtype=str).fillna("")
    ids = pub.loc[pub["decisao"] == "publicar", "id"].tolist()
    todos = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    temp = 0.0 if RUNS_PER_MODEL == 1 else TEMPERATURE
    novas = 0
    for i in ids:
        p = J.montar_prompt(arv, q.loc[i], todos)
        k = hashlib.sha256(f"{JUDGE_BACKEND}|{MODELO}|{temp}|0|{p}".encode()).hexdigest()
        if not (J.JCACHE / f"{k}.json").exists():
            novas += 1
    print(f"{len(ids)} publicadas | chamadas novas: {novas} | ~{novas * 9000 / 1e6:.1f} M tokens de entrada")
    if not rodar:
        print("Dry-run. Rode com --rodar para executar.")
        return

    gerar = None
    cache_ctx = None
    if os.getenv("CONTEXT_CACHE", "").strip().lower() in ("1", "true", "sim", "yes"):
        from src.contexto_cache import GeradorCache

        cache_ctx = GeradorCache(arv, MODELO)
        gerar = cache_ctx
        print(f"cache de contexto ligado (prefixo enviado 1x): {cache_ctx.nome() or '(criado na 1a chamada)'}")

    def um(i):
        return {"id": i, "vote": J.uma_chamada(arv, q.loc[i], todos, MODELO, 0, gerar=gerar)}

    with ThreadPoolExecutor(max_workers=JUDGE_WORKERS) as ex:
        res = list(ex.map(um, ids))
    with open(OUT / "votos_verificacao.jsonl", "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if cache_ctx is not None:
        print("cache de contexto stats:", cache_ctx.stats)
        cache_ctx.fechar()

    pubt = pub.set_index("id")["tema_central_id"]

    def concorda(i, v):
        t = pubt[i]
        if v["fora"] or not v["tema_id"]:
            return False
        if arv.relacionado(t, v["tema_id"]):
            return True
        return bool(arv.parent.get(t)) and arv.parent.get(t) == arv.parent.get(v["tema_id"])

    c = {"concorda": 0, "discorda": 0, "fora": 0, "invalido": 0}
    for r in res:
        v = r["vote"]
        if v["fora"]:
            c["fora"] += 1
        elif not v["tema_id"]:
            c["invalido"] += 1
        elif concorda(r["id"], v):
            c["concorda"] += 1
        else:
            c["discorda"] += 1
    print("Verificador contra o tema publicado:", c, "| STATS:", J.STATS)

    rp = OUT / "amostra_rotulagem.csv"
    if rp.exists():
        rot = pd.read_csv(rp, dtype=str).fillna("")
        rot = rot[rot["tema_correto_id"] != ""].set_index("id")["tema_correto_id"]
        tab = {}
        for r in res:
            if r["id"] in rot.index:
                certo = arv.relacionado(pubt[r["id"]], rot[r["id"]])
                chave = ("publicada certa" if certo else "publicada errada",
                         "verificador concorda" if concorda(r["id"], r["vote"]) else "verificador discorda")
                tab[chave] = tab.get(chave, 0) + 1
        print("Na amostra rotulada (rotulos do DeepSeek):")
        for k, n in sorted(tab.items()):
            print("  ", k, n)

    from src import uso
    uso.registrar("verificar_arvore", J.STATS, extra={"publicadas": len(ids), "modelo": MODELO})


if __name__ == "__main__":
    main()
