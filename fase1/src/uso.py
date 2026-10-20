"""Instrumentacao de uso: tokens e latencia por etapa, em log append-only.

Motivo: src/judge.py grava outputs/uso.json, mas ele e sobrescrito a cada run (so o
ultimo fica registrado) e as etapas `fallback_arvore` e `verificar_arvore` nao gravavam
nada. Aqui qualquer etapa pode registrar um evento; o arquivo acumula, entao duas
execucoes nao se apagam.

  outputs/uso_etapas.jsonl   # um JSON por execucao de etapa

Campos por linha: quando, etapa, chamadas, cache, tokens_in, tokens_out,
tokens_pensando, erros, segundos, + campos `extra` da etapa.

Valores ausentes ficam como null (nao estimamos o que nao foi medido).
"""
import json
import time
from datetime import datetime, timezone

from src.config import OUT

ARQ = OUT / "uso_etapas.jsonl"
_CAMPOS = ("chamadas", "cache", "tokens_in", "tokens_out", "tokens_pensando", "erros")


def registrar(etapa, stats=None, segundos=None, extra=None):
    stats = dict(stats or {})
    reg = {
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "etapa": etapa,
    }
    for k in _CAMPOS:
        reg[k] = stats.get(k)
    reg["segundos"] = segundos if segundos is not None else stats.get("segundos")
    if "modelos" in stats:
        reg["modelos"] = stats["modelos"]
    if "rodadas_por_modelo" in stats:
        reg["rodadas_por_modelo"] = stats["rodadas_por_modelo"]
    if extra:
        reg.update(extra)
    with open(ARQ, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg


def cronometro():
    return time.time()


def ler():
    if not ARQ.exists():
        return []
    return [json.loads(l) for l in ARQ.open(encoding="utf-8") if l.strip()]


def resumo():
    """Soma o consumo registrado por etapa (o que foi medido; null = nao medido)."""
    tot = {}
    for r in ler():
        e = tot.setdefault(r["etapa"], {"execucoes": 0, "tokens_in": 0, "tokens_out": 0,
                                        "tokens_pensando": 0, "chamadas": 0, "segundos": 0.0})
        e["execucoes"] += 1
        for k in ("tokens_in", "tokens_out", "tokens_pensando", "chamadas"):
            if r.get(k):
                e[k] += r[k]
        if r.get("segundos"):
            e["segundos"] += r["segundos"]
    return tot


if __name__ == "__main__":
    print(json.dumps(resumo(), ensure_ascii=False, indent=2))
