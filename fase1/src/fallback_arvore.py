"""Etapa 2c: fallback com a arvore inteira.

Quando algum voto disse 'fora' e a questao nao foi publicada, o juiz recebe
todos os temas (sem busca). Isto muda outputs/candidatos.json, entao a operacao
e reversivel e vem desligada por padrao.

  python -m src.fallback_arvore            dry-run: mostra o que mudaria
  python -m src.fallback_arvore --apply    grava (com backup automatico)
  python -m src.fallback_arvore --restore  desfaz o ultimo fallback aplicado

Variavel FALLBACK_IDS=Q1,Q2 limita a um subconjunto (util para testar).

Backups:
  outputs/backups/candidatos.before_fallback.<timestamp>.json  copia integral
  outputs/fallback_originais.json                              listas originais por id
"""
import argparse
import json
from datetime import datetime

import pandas as pd

from src.config import OUT, ROOT
from src.temas import Arvore

BACKUPS = OUT / "backups"
ORIGINAIS = OUT / "fallback_originais.json"


def _ids_alvo():
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    nao_pub = set(pub.loc[pub["decisao"] != "publicar", "id"])
    ids = []
    with open(OUT / "votos.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["id"] in nao_pub and any(v.get("fora") for v in r["votes"]):
                ids.append(r["id"])
    import os

    so = os.getenv("FALLBACK_IDS")
    if so:
        ids = [i for i in ids if i in set(so.split(","))]
    return sorted(ids)


def _backup(cand):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (BACKUPS / f"candidatos.before_fallback.{ts}.json").write_text(
        json.dumps(cand, ensure_ascii=False), encoding="utf-8"
    )
    return BACKUPS / f"candidatos.before_fallback.{ts}.json"


def aplicar():
    arv = Arvore()
    ids = _ids_alvo()
    todos = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    cand = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    originais = {}
    if ORIGINAIS.exists():
        try:
            originais = json.loads(ORIGINAIS.read_text(encoding="utf-8"))
        except Exception:
            originais = {}
    bkp = _backup(cand)
    for qid in ids:
        if qid not in cand:
            continue
        if qid not in originais:
            originais[qid] = cand[qid].get("candidatos", [])
        cand[qid]["candidatos"] = list(todos)
        cand[qid]["fallback_arvore_inteira"] = True
    (OUT / "candidatos.json").write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")
    ORIGINAIS.write_text(json.dumps(originais, ensure_ascii=False), encoding="utf-8")
    chars = sum(len(arv.caminho[t]) + 8 for t in todos)
    print(f"Aplicado: {len(ids)} questoes com a arvore inteira ({len(todos)} temas, ~{chars // 3} tokens por prompt).")
    print(f"Backup integral: {bkp}")
    print(f"Originais por id: {ORIGINAIS}")
    print(sorted(ids))
    from src import uso
    uso.registrar("fallback_arvore", extra={
        "questoes_alteradas": len(ids),
        "temas_arvore_inteira": len(todos),
        "estimativa_tokens_prompt": (chars // 3) * len(ids),  # ESTIMATIVA (nao medido)
        "observacao": "etapa sem chamadas de API; o custo ocorre no judge seguinte",
    })


def restore():
    if not ORIGINAIS.exists():
        print(f"Nada para restaurar: {ORIGINAIS} nao existe.")
        return
    originais = json.loads(ORIGINAIS.read_text(encoding="utf-8"))
    cand = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    _backup(cand)
    for qid, ids in originais.items():
        if qid in cand:
            cand[qid]["candidatos"] = ids
            cand[qid].pop("fallback_arvore_inteira", None)
    (OUT / "candidatos.json").write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")
    ORIGINAIS.unlink()
    print(f"Restaurados {len(originais)} candidatos ao estado anterior.")


def dry_run():
    arv = Arvore()
    ids = _ids_alvo()
    todos = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    cand = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    ja = [q for q in ids if cand.get(q, {}).get("fallback_arvore_inteira")]
    chars = sum(len(arv.caminho[t]) + 8 for t in todos)
    print(f"[dry-run] {len(ids)} questoes seriam trocadas pela arvore inteira "
          f"({len(todos)} temas, ~{chars // 3} tokens por prompt).")
    print(f"[dry-run] {len(ja)} delas ja estao com a arvore inteira (sem mudanca).")
    print("[dry-run] Rode com --apply para gravar (cria backup automatico).")
    print(sorted(ids))


def main():
    ap = argparse.ArgumentParser(description="Fallback com a arvore inteira (reversivel).")
    ap.add_argument("--apply", action="store_true", help="grava as mudancas (default: dry-run)")
    ap.add_argument("--restore", action="store_true", help="desfaz o fallback aplicado")
    args = ap.parse_args()
    if args.restore:
        restore()
    elif args.apply:
        aplicar()
    else:
        dry_run()


if __name__ == "__main__":
    main()
