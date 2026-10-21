"""Checagens mecanicas das tabelas propostas por LLM (sem validacao juridica).

Uso, da pasta fase2/:
    python -m src.experimentos.checar_tabelas
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.config import ARTEFATOS, DATA, ROOT
from src.temas import Arvore


ART = ROOT / "experimentos" / "artigos_tema.csv"
LEIS = ROOT / "experimentos" / "leis_tema.csv"
OUT = ARTEFATOS / "experimentos"
OUT.mkdir(parents=True, exist_ok=True)


def parse_artigo(valor: str):
    """'121-A' -> (121, 'A'); '395' -> (395, ''). Devolve None se nao casar."""
    m = re.fullmatch(r"\s*(\d+)(?:-([A-Za-z]+))?\s*", str(valor))
    if not m:
        return None
    return int(m.group(1)), (m.group(2) or "").upper()


def chave(valor: str):
    p = parse_artigo(valor)
    if p is None:
        return None
    base, suf = p
    return (base, suf)


def ordem(valor: str):
    """Ordem dentro do mesmo numero de artigo: sem sufixo antes de A, B, ..."""
    p = parse_artigo(valor)
    if p is None:
        return None
    base, suf = p
    return (base, suf if suf else "")


def art_set(valor_inicio: str, valor_fim: str):
    """Conjunto de (numero, sufixo) que a linha cobre.

    A regra do PROVENIENCIA e aplicada aqui: 121 e 121-A sao artigos distintos.
    Uma faixa mista como 317..318-B cobre 317 sem sufixo e 318, 318-A, 318-B.
    """
    ini, fim = parse_artigo(valor_inicio), parse_artigo(valor_fim)
    if ini is None or fim is None or ini > fim:
        return set()
    b0, s0 = ini
    b1, s1 = fim
    alfabeto = [""] + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    out = set()
    for base in range(b0, b1 + 1):
        if base == b0 and base == b1:
            sufs = alfabeto[alfabeto.index(s0):alfabeto.index(s1) + 1]
        elif base == b0:
            sufs = alfabeto[alfabeto.index(s0):]
        elif base == b1:
            sufs = alfabeto[:alfabeto.index(s1) + 1]
        else:
            sufs = [""]
        for suf in sufs:
            out.add((base, suf))
    return out


def normaliza_lei(valor: str) -> str:
    """'11.340/2006' e 'Lei nº 9.099' viram apenas os digitos do numero."""
    m = re.search(r"(\d[\d\.]*)", str(valor))
    return m.group(1).replace(".", "") if m else ""


def main():
    temas = pd.read_csv(DATA / "temas.csv", dtype=str).fillna("")
    ativos = set(temas.loc[temas["status"] == "active", "tema_id"])
    arv = Arvore()
    art = pd.read_csv(ART, dtype=str).fillna("")
    leis = pd.read_csv(LEIS, dtype=str).fillna("")

    problemas = []
    revisao = []

    def add(tabela, linha, motivo, detalhe=""):
        item = {"tabela": tabela, "linha": linha, "motivo": motivo, "detalhe": detalhe}
        problemas.append(item)
        if motivo not in ("tema_inexistente",):
            revisao.append(item)

    # ---------------------------------------------------------- temas
    invalidos_art = []
    for i, r in art.iterrows():
        if r["tema_id"] not in set(temas["tema_id"]):
            invalidos_art.append({"linha": i + 2, "tema_id": r["tema_id"]})
            add("artigos_tema.csv", i + 2, "tema_inexistente", r["tema_id"])
        elif r["tema_id"] not in ativos:
            add("artigos_tema.csv", i + 2, "tema_inativo", r["tema_id"])

    invalidos_leis = []
    for i, r in leis.iterrows():
        if r["tema_id"] not in set(temas["tema_id"]):
            invalidos_leis.append({"linha": i + 2, "tema_id": r["tema_id"]})
            add("leis_tema.csv", i + 2, "tema_inexistente", r["tema_id"])
        elif r["tema_id"] not in ativos:
            add("leis_tema.csv", i + 2, "tema_inativo", r["tema_id"])

    # ------------------------------------------------- faixas por codigo
    fora_ordem = []
    sobrepostas = []
    base_compartilhada = []
    for codigo, g in art.groupby("codigo", sort=True):
        linhas = []
        for i, r in g.iterrows():
            ini, fim = chave(r["art_inicio"]), chave(r["art_fim"])
            if ini is None or fim is None:
                add("artigos_tema.csv", i + 2, "faixa_ilegivel",
                    f"{r['art_inicio']}..{r['art_fim']}")
                continue
            conjunto = art_set(r["art_inicio"], r["art_fim"])
            linhas.append((i + 2, r, conjunto))
            if ini > fim:
                fora_ordem.append({"codigo": codigo, "linha": i + 2,
                                   "inicio": r["art_inicio"], "fim": r["art_fim"]})
                add("artigos_tema.csv", i + 2, "faixa_fora_de_ordem",
                    f"{r['art_inicio']} > {r['art_fim']}")
        for a in range(len(linhas)):
            la, ra, ca = linhas[a]
            for b in range(a + 1, len(linhas)):
                lb, rb, cb = linhas[b]
                # Sobreposicao real na identidade do artigo (numero + sufixo).
                if ca & cb:
                    sobrepostas.append({
                        "codigo": codigo,
                        "linha_a": la, "faixa_a": f"{ra['art_inicio']}..{ra['art_fim']}",
                        "tema_a": ra["tema_id"],
                        "linha_b": lb, "faixa_b": f"{rb['art_inicio']}..{rb['art_fim']}",
                        "tema_b": rb["tema_id"],
                        "interseccao": sorted(ca & cb)[:8],
                    })
                    add("artigos_tema.csv", la, "faixa_sobreposta_real",
                        f"{ra['art_inicio']}..{ra['art_fim']} x "
                        f"{rb['art_inicio']}..{rb['art_fim']} (linha {lb})")
                # O mesmo numero com e sem sufixo e esperado pela regra; fica
                # registrado como informativo, nao como erro mecanico.
                bases_a = {x[0] for x in ca}
                bases_b = {x[0] for x in cb}
                if bases_a & bases_b and not (ca & cb):
                    base_compartilhada.append({
                        "codigo": codigo, "linha_a": la, "linha_b": lb,
                        "bases": sorted(bases_a & bases_b),
                    })

    # ------------------------------------------------------- sufixos
    sufixos = []
    bases_com_faixa = defaultdict(list)
    for i, r in art.iterrows():
        ini, fim = parse_artigo(r["art_inicio"]), parse_artigo(r["art_fim"])
        if ini is None or fim is None:
            continue
        if not ini[1] and not fim[1]:
            for b in range(ini[0], fim[0] + 1):
                bases_com_faixa[(r["codigo"], b)].append(i + 2)
    for i, r in art.iterrows():
        ini, fim = parse_artigo(r["art_inicio"]), parse_artigo(r["art_fim"])
        if ini is None or fim is None or (not ini[1] and not fim[1]):
            continue
        sufixos.append({"linha": i + 2, "codigo": r["codigo"],
                        "inicio": r["art_inicio"], "fim": r["art_fim"],
                        "tema_id": r["tema_id"]})
        if ini[0] != fim[0]:
            add("artigos_tema.csv", i + 2, "sufixo_atravessa_numeros",
                f"{r['art_inicio']}..{r['art_fim']}")
        if bool(ini[1]) != bool(fim[1]):
            add("artigos_tema.csv", i + 2, "sufixo_misto",
                f"{r['art_inicio']}..{r['art_fim']}")
        if ini[1] and fim[1] and ini[1] > fim[1]:
            add("artigos_tema.csv", i + 2, "sufixo_fora_de_ordem",
                f"{r['art_inicio']} > {r['art_fim']}")
        # A regra do PROVENIENCIA diz que sufixo casa so com a linha de mesmo
        # sufixo. Se existir uma faixa sem sufixo cobrindo o mesmo numero, a
        # tabela fica ambigua e precisa de decisao humana.
        for base in range(ini[0], fim[0] + 1):
            if bases_com_faixa[(r["codigo"], base)]:
                base_compartilhada.append({
                    "codigo": r["codigo"], "linha_a": i + 2,
                    "linha_b": bases_com_faixa[(r["codigo"], base)],
                    "bases": [base], "informativo": "sufixo vs faixa sem sufixo",
                })

    # --------------------------------------- linhas da correcao 5155
    catalogo = []
    for i, r in art.iterrows():
        obs = str(r.get("observacao", ""))
        if "catalogo original" in obs.lower() or "tema irmao de 5155" in obs.lower():
            item = {"linha": i + 2, "codigo": r["codigo"],
                    "faixa": f"{r['art_inicio']}..{r['art_fim']}",
                    "tema_id": r["tema_id"], "observacao": obs}
            catalogo.append(item)
            if r["tema_id"] not in ativos:
                add("artigos_tema.csv", i + 2, "catalogo_tema_inativo", r["tema_id"])
            pai = arv.parent.get(r["tema_id"])
            item["pai_atual"] = pai
            if pai != "5155":
                add("artigos_tema.csv", i + 2, "catalogo_pai_nao_5155",
                    f"{r['tema_id']} -> {pai}")

    # --------------------------------------------------------- leis
    numeros = defaultdict(list)
    for i, r in leis.iterrows():
        n = normaliza_lei(r["lei"])
        numeros[n].append(i + 2)
        if not n:
            add("leis_tema.csv", i + 2, "lei_ilegivel", r["lei"])
        if "revogada" in str(r.get("observacao", "")).lower():
            add("leis_tema.csv", i + 2, "lei_revogada_revisar", r["observacao"])
    repetidas = {n: ls for n, ls in numeros.items() if n and len(ls) > 1}

    resumo = {
        "artigos_linhas": len(art),
        "leis_linhas": len(leis),
        "temas_ativos": len(ativos),
        "temas_invalidos_artigos": invalidos_art,
        "temas_invalidos_leis": invalidos_leis,
        "fora_de_ordem": fora_ordem,
        "sobreposicoes": sobrepostas,
        "base_compartilhada": base_compartilhada,
        "sufixos": sufixos,
        "catalogo_original": catalogo,
        "leis_repetidas": repetidas,
        "problemas": problemas,
        "revisao_humana": revisao,
    }
    (OUT / "checagem_tabelas.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Relatorio curto para leitura humana.
    linhas = ["# Checagem mecanica das tabelas", ""]
    linhas.append(f"- linhas em artigos_tema.csv: {len(art)}")
    linhas.append(f"- linhas em leis_tema.csv: {len(leis)}")
    linhas.append(f"- temas inexistentes: {len(invalidos_art) + len(invalidos_leis)}")
    linhas.append(f"- faixas fora de ordem: {len(fora_ordem)}")
    linhas.append(f"- sobreposicoes reais: {len(sobrepostas)}")
    linhas.append(f"- numeros compartilhados com e sem sufixo: {len(base_compartilhada)} (esperado pela regra)")
    linhas.append(f"- linhas com sufixo: {len(sufixos)}")
    linhas.append(f"- linhas de catalogo original: {len(catalogo)}")
    linhas.append(f"- leis repetidas: {len(repetidas)}")
    linhas += ["", "## Revisao humana", ""]
    if not revisao:
        linhas.append("Nenhum item mecanico pendente.")
    for x in revisao:
        linhas.append(f"- {x['tabela']} linha {x['linha']}: {x['motivo']} ({x['detalhe']})")
    (OUT / "checagem_tabelas.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")

    print(json.dumps({"resumo": {k: v for k, v in resumo.items() if not isinstance(v, list)},
                      "n_problemas": len(problemas),
                      "n_revisao_humana": len(revisao)}, ensure_ascii=False, indent=2))
    print(f"Relatorios: {OUT / 'checagem_tabelas.json'} e .md")


if __name__ == "__main__":
    main()
