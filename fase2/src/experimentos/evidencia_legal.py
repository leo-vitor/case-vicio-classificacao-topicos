"""Extrator deterministico de evidencia legal (sem LLM).

Le, em cada questao, artigos do CP/CPP e numeros de lei especial, mapeia para
temas do catalogo pelas tabelas propostas e separa quatro fontes:

  CP_PG   CP, arts. 1 a 120 (Parte Geral)
  CP_PE   CP, arts. 121 em diante (Parte Especial)
  CPP     Codigo de Processo Penal
  LEI     lei especial, pelo numero (leis_tema.csv)

O extrator nao decide nada e nao olha a folha-verdade. A saida e uma foto por
questao: citacoes encontradas, ramos indicados e se ha um ramo unico.

Uso, da pasta fase2/:
    python -m src.experimentos.evidencia_legal
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.artefato import tema1
from src.config import ARTEFATOS, DATA, ROOT
from src.experimentos.checar_tabelas import art_set, normaliza_lei, parse_artigo
from src.temas import Arvore


ART = ROOT / "experimentos" / "artigos_tema.csv"
LEIS = ROOT / "experimentos" / "leis_tema.csv"
OUT = ARTEFATOS / "experimentos"
OUT.mkdir(parents=True, exist_ok=True)

# Prefixos de artigo. O grupo seguinte aceita listas ("395 e 396") e sufixos
# ("121-A"), mas para no primeiro sinal que nao seja numero ou conector.
ART_RE = re.compile(
    r"\b(?:art(?:igo)?s?\.?)\s*"
    r"((?:\d{1,4}(?:-[A-Za-z])?)"
    r"(?:\s*(?:,|e|a|até|ao|à)\s*\d{1,4}(?:-[A-Za-z])?)*)",
    re.IGNORECASE,
)
NUM_RE = re.compile(r"\d{1,4}(?:-[A-Za-z])?")
LEI_RE = re.compile(
    r"\bLei\s*(?:n[º°o.]*|n[úu]mero)?\s*"
    r"(\d[\d\.]*)\s*(?:/\s*(\d{2,4}))?",
    re.IGNORECASE,
)

# Codigos que a tabela cobre. CPP vem antes de CP para o caso de "CPP".
CODE_PATTERNS = [
    ("CPP", re.compile(
        r"(?<![A-Za-z])(?:CPP|C[óo]digo\s+de\s+Processo\s+Penal|"
        r"C[óo]digo\s+Processual\s+Penal|"
        r"Decreto(?:-Lei)?\s*(?:n[º°o.]*)?\s*3\.?689)(?![A-Za-z])",
        re.IGNORECASE)),
    ("CP", re.compile(
        r"(?<![A-Za-z])(?:CP|C[óo]digo\s+Penal|C[óo]dex|"
        r"Estatuto\s+Repressivo|Decreto(?:-Lei)?\s*(?:n[º°o.]*)?\s*2\.?848)"
        r"(?!\s+Militar)(?![A-Za-z])",
        re.IGNORECASE)),
]


def carregar_tabelas():
    art = pd.read_csv(ART, dtype=str).fillna("")
    leis = pd.read_csv(LEIS, dtype=str).fillna("")
    art_map = defaultdict(list)
    for _, r in art.iterrows():
        art_map[r["codigo"]].append((r["art_inicio"], r["art_fim"], r["tema_id"], r["observacao"]))
    lei_map = {}
    for _, r in leis.iterrows():
        n = normaliza_lei(r["lei"])
        if n:
            lei_map[n] = (r["tema_id"], r["observacao"])
    return art_map, lei_map


def codigo_mais_proximo(texto: str, ini: int, fim: int, janela: int = 180):
    """Codigo citado mais perto do trecho, com o texto como unica fonte."""
    candidatos = []
    for codigo, rx in CODE_PATTERNS:
        for m in rx.finditer(texto):
            if m.start() < ini - janela or m.start() > fim + janela:
                continue
            # Distancia ao fim da lista quando o codigo vem depois; ao inicio
            # quando vem antes. Assim "art. 121 do CP" e "CP, art. 121" ambos
            # funcionam sem escolher um codigo de outra oracao.
            d = m.start() - fim if m.start() >= fim else ini - m.end()
            candidatos.append((abs(d), 0 if m.start() >= fim else 1, codigo))
    if not candidatos:
        return None
    return min(candidatos)[2]


def mapear_artigo(art_map, arv, codigo: str, valor: str):
    p = parse_artigo(valor)
    if p is None:
        return []
    base, suf = p
    achados = []
    for ini, fim, tema_id, obs in art_map.get(codigo, []):
        conjunto = art_set(ini, fim)
        if (base, suf) not in conjunto:
            continue
        ramo = tema1(arv, tema_id)
        achados.append({
            "codigo": codigo, "artigo": valor, "base": base, "sufixo": suf,
            "tema_id": tema_id, "ramo": ramo,
            "fonte": ("CP_PG" if codigo == "CP" and base <= 120
                      else "CP_PE" if codigo == "CP" else "CPP"),
            "observacao": obs,
        })
    return achados


def extrair_questao(arv, art_map, lei_map, qid: str, texto: str):
    achados = []
    for m in ART_RE.finditer(texto):
        codigo = codigo_mais_proximo(texto, m.start(), m.end())
        if not codigo:
            continue
        for valor in NUM_RE.findall(m.group(1)):
            achados.extend(mapear_artigo(art_map, arv, codigo, valor))

    leis = []
    for m in LEI_RE.finditer(texto):
        n = m.group(1).replace(".", "")
        if n in lei_map:
            tema_id, obs = lei_map[n]
            ramo = tema1(arv, tema_id)
            leis.append({"lei": m.group(0).strip(), "numero": n,
                         "tema_id": tema_id, "ramo": ramo,
                         "fonte": "LEI", "observacao": obs})

    fontes = sorted({x["fonte"] for x in achados} | {"LEI"} if leis else {x["fonte"] for x in achados})
    ramos = defaultdict(set)
    for x in achados + leis:
        if x.get("ramo"):
            ramos[x["fonte"]].add(x["ramo"])
    ramos = {k: sorted(v) for k, v in sorted(ramos.items())}
    todos = sorted({r for v in ramos.values() for r in v})
    return {
        "id": qid,
        "fontes": fontes,
        "artigos": achados,
        "leis": leis,
        "ramos_por_fonte": ramos,
        "ramos_geral": todos,
        "ramo_unico_geral": len(todos) == 1,
        "ramo_unico_por_fonte": {k: (v[0] if len(v) == 1 else None) for k, v in ramos.items()},
        "tem_evidencia": bool(todos),
    }


def resumo_cobertura(rows, ids_folha):
    total = len(rows)
    folha = [r for r in rows if r["id"] in ids_folha]

    def conta(rs, pred):
        return sum(1 for r in rs if pred(r))

    def bloco(rs, rotulo):
        n = len(rs)
        return {
            "conjunto": rotulo, "n": n,
            "com_evidencia": conta(rs, lambda r: r["tem_evidencia"]),
            "ramo_unico_geral": conta(rs, lambda r: r["ramo_unico_geral"]),
            "com_cp_pg": conta(rs, lambda r: "CP_PG" in r["ramos_por_fonte"]),
            "com_cp_pe": conta(rs, lambda r: "CP_PE" in r["ramos_por_fonte"]),
            "com_cpp": conta(rs, lambda r: "CPP" in r["ramos_por_fonte"]),
            "com_lei": conta(rs, lambda r: "LEI" in r["ramos_por_fonte"]),
            "unico_cp_pg": conta(rs, lambda r: r["ramo_unico_por_fonte"].get("CP_PG") is not None),
            "unico_cp_pe": conta(rs, lambda r: r["ramo_unico_por_fonte"].get("CP_PE") is not None),
            "unico_cpp": conta(rs, lambda r: r["ramo_unico_por_fonte"].get("CPP") is not None),
            "unico_lei": conta(rs, lambda r: r["ramo_unico_por_fonte"].get("LEI") is not None),
        }

    return {"total": bloco(rows, "659"), "folha": bloco(folha, "folha-verdade")}


def main():
    arv = Arvore()
    art_map, lei_map = carregar_tabelas()
    q = pd.read_csv(ARTEFATOS / "questoes_limpas.csv", dtype=str).fillna("")
    folha = pd.read_csv(DATA / "folha_verdade.csv", dtype=str).fillna("")
    ids_folha = set(folha["id"])
    rows = [extrair_questao(arv, art_map, lei_map, r.id, r.texto) for r in q.itertuples()]

    # CSV achatado, para as etapas seguintes; JSONL preserva os detalhes.
    flat = []
    for r in rows:
        flat.append({
            "id": r["id"],
            "fontes": ";".join(r["fontes"]),
            "ramos_geral": ";".join(r["ramos_geral"]),
            "ramo_unico_geral": int(r["ramo_unico_geral"]),
            "tem_evidencia": int(r["tem_evidencia"]),
            "ramos_por_fonte": json.dumps(r["ramos_por_fonte"], ensure_ascii=False),
            "ramo_unico_por_fonte": json.dumps(r["ramo_unico_por_fonte"], ensure_ascii=False),
            "n_artigos": len(r["artigos"]),
            "n_leis": len(r["leis"]),
            "artigos": json.dumps(r["artigos"], ensure_ascii=False),
            "leis": json.dumps(r["leis"], ensure_ascii=False),
        })
    pd.DataFrame(flat).to_csv(OUT / "evidencia_legal.csv", index=False)
    with (OUT / "evidencia_legal.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cobertura = resumo_cobertura(rows, ids_folha)
    (OUT / "evidencia_legal_cobertura.json").write_text(
        json.dumps(cobertura, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(cobertura, ensure_ascii=False, indent=2))
    print(f"Saidas: {OUT / 'evidencia_legal.csv'} e .jsonl")


if __name__ == "__main__":
    main()
