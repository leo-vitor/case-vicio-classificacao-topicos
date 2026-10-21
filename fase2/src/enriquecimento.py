"""Leitura do artefato de enriquecimento (offline, versionado).

O pipeline nao chama LLM: o artefato e um JSONL de 351 objetos, gerado uma vez e
congelado por hash. Aqui ficam o carregador e a definicao de `texto_tema` enriquecido,
para que `pisos.py`, `cascata.py` e `decisao.py` usem exatamente o mesmo texto.

Variante adotada (ver docs/etapa2_pisos.md): `caminho + titulo + sinonimos + institutos +
texto_enriquecido`. Os campos sao separados por espaco; nao ha peso por campo — a ablage
mostrou que o ganho vem da combinacao, e ponderar exigiria um parametro a mais sem
respaldo em 92 questoes.
"""
import hashlib
import json

from src.config import ROOT
from src.recuperacao import texto_tema as texto_base

PADRAO = ROOT / "enriquecimento_v01.jsonl"


def carregar(path=None) -> dict:
    p = PADRAO if path is None else path
    out = {}
    if not p.exists():
        return out
    for linha in p.read_text(encoding="utf-8").splitlines():
        if linha.strip():
            o = json.loads(linha)
            out[str(o["id_tema"])] = o
    return out


def versao(path=None) -> str:
    p = PADRAO if path is None else path
    if not p.exists():
        return "vazio"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def texto_tema(arv, tid, enr) -> str:
    """Caminho + titulo + (sinonimos + institutos + texto). Sem artefato, cai na base."""
    base = texto_base(arv, tid)
    o = enr.get(str(tid))
    if not o:
        return base
    extra = " ".join(
        list(o.get("sinonimos", [])) + list(o.get("institutos", [])) + [o.get("texto_enriquecido", "")]
    ).strip()
    return (base + " " + extra).strip() if extra else base


def textos(arv, pool, enr) -> list:
    return [texto_tema(arv, t, enr) for t in pool]
