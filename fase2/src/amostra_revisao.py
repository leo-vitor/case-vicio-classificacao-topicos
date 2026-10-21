"""Monta a amostra de 30 objetos para a revisao juridica humana (Experimento 4).

A amostra e pre-registrada: os estratos e o criterio de aceitacao estao em
`docs/revisao_juridica.md` e nao mudam depois de ver o resultado.

Estratos (30 objetos, sem repeticao):
  - ate 8 em colisoes de vocabulario entre irmaos (avisos do contrato);
  - os 3 nos da correcao de taxonomia v02 (5148, 5155, 5156);
  - 6 de Legislacao Especial, 5 de Criminologia, 5 de Penal/Processo Penal;
  - o restante aleatorio (seed fixa).

Gera dois arquivos:
  artefatos/revisao_30.csv        controle: estrato, ordem, rubrica vazia
  artefatos/revisao_30_cego.csv   folha do revisor: sem estrato nem confianca,
                                  ordem embaralhada + 3 duplicatas cegas no fim

Uso (da pasta fase2/):
    python -m src.amostra_revisao
"""
import json

import numpy as np
import pandas as pd

from src.artefato import tema1
from src.config import ARTEFATOS, SEED
from src.temas import Arvore

RUBRICA = ["r1_precisao", "r2_discriminacao", "r3_cobertura", "r4_risco"]
VAZIAS = RUBRICA + ["veredito", "comentario"]
N = 30
N_CEGAS = 3


def termos(o):
    out = set()
    for chave in ("sinonimos", "institutos"):
        for t in o.get(chave) or []:
            if isinstance(t, str) and t.strip():
                out.add(t.strip().lower())
    return out


def colisoes_entre_irmaos(arv, artefato):
    """Objetos em colisao de vocabulario com irmao (mesmo pai na arvore efetiva)."""
    por_pai = {}
    for tid in artefato:
        pai = arv.parent.get(tid)
        if pai:
            por_pai.setdefault(pai, []).append(tid)
    achados = set()
    for grupo in por_pai.values():
        for i, a in enumerate(grupo):
            for b in grupo[i + 1:]:
                if termos(artefato[a]) & termos(artefato[b]):
                    achados.update((a, b))
    return sorted(achados)


def main():
    arv = Arvore()
    artefato = {str(json.loads(l)["id_tema"]): json.loads(l)
                for l in (ARTEFATOS.parent / "enriquecimento_v01.jsonl")
                .read_text(encoding="utf-8").splitlines() if l.strip()}
    rng = np.random.default_rng(SEED)

    escolhidos, estrato = [], {}

    def add(ids, nome, limite=None):
        n = 0
        for t in ids:
            if limite is not None and n >= limite:
                break
            if t in artefato and t not in estrato:
                estrato[t] = nome
                escolhidos.append(t)
                n += 1

    add(colisoes_entre_irmaos(arv, artefato), "colisao entre irmaos", 8)
    add(["5148", "5155", "5156"], "taxonomia v02")

    def amostrar(pool, n, nome):
        disp = [t for t in pool if t not in estrato]
        add(list(rng.choice(disp, size=min(n, len(disp)), replace=False)), nome)

    le = sorted(t for t in artefato if "4684" <= t <= "4709")
    amostrar(le, 6, "legislacao especial")

    crim = sorted(t for t in artefato if "4366" <= t <= "4390")
    amostrar(crim, 5, "criminologia")

    pen = sorted(t for t in artefato if "5063" <= t <= "5233")
    amostrar(pen, 3, "penal")
    pp = sorted(t for t in artefato if "5466" <= t <= "5590")
    amostrar(pp, 2, "processo penal")

    resto = [t for t in sorted(artefato) if t not in estrato]
    amostrar(resto, N - len(escolhidos), "aleatorio")

    assert len(escolhidos) == N, len(escolhidos)

    ordem = list(rng.permutation(escolhidos))
    linhas = []
    for i, tid in enumerate(ordem, start=1):
        o = artefato[tid]
        linhas.append({
            "ordem": i,
            "id_tema": tid,
            "titulo": o.get("titulo") or arv.titulo.get(tid, ""),
            "ramo": arv.titulo.get(tema1(arv, tid), ""),
            "sinonimos": "; ".join(o.get("sinonimos") or []),
            "institutos": "; ".join(o.get("institutos") or []),
            "texto_enriquecido": o.get("texto_enriquecido") or "",
            "distincoes": " | ".join(
                f"vs {d.get('id_tema')}: {d.get('diferenca')}"
                for d in o.get("distincoes") or []),
            "estrato": estrato[tid],
            **{c: "" for c in VAZIAS},
        })

    controle = pd.DataFrame(linhas)
    controle.to_csv(ARTEFATOS / "revisao_30.csv", index=False)

    # folha do revisor: sem estrato, ordem ja embaralhada, 3 duplicatas cegas
    cego = controle.drop(columns=["estrato"]).copy()
    dup = cego.sample(n=N_CEGAS, random_state=SEED).copy()
    dup["duplicata_de"] = dup["ordem"]
    dup["ordem"] = range(N + 1, N + 1 + N_CEGAS)
    cego["duplicata_de"] = ""
    cego = pd.concat([cego, dup], ignore_index=True)
    cego.to_csv(ARTEFATOS / "revisao_30_cego.csv", index=False)

    print("amostra:", N, "| cegas:", N_CEGAS)
    print(controle.groupby("estrato").size().to_string())
    print("\narquivos:")
    print(" ", ARTEFATOS / "revisao_30.csv")
    print(" ", ARTEFATOS / "revisao_30_cego.csv")


if __name__ == "__main__":
    main()
