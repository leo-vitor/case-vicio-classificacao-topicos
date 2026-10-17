"""Desempenho do PIPELINE CONGELADO em uma NOVA rotulagem (offline, sem API).

Le `publicacao.csv` (decisao ja tomada por questao) e um arquivo de rotulos
(ex.: `data/rotulos_opus.tsv`) e mede, nas questoes rotuladas:

  - distribuicao de decisao (publicar / revisar / fora)
  - entre as PUBLICADAS: concordancia EXATA e HIERARQUICA (tema/pai/filho) e escolha de GEMEO
  - entre as NAO publicadas: o tema correto estava entre os candidatos? (era recuperavel?)
  - concordancia por nivel de 'duvida' do rotulo (baixa/media/alta), quando existir
  - concordancia LENIENTE contando tambem o campo 'alternativo' (quando existir)
  - acordo com OUTRA rotulagem (--comparar) nas questoes em comum

Nao altera nada do pipeline entregue. Saida em outputs/experimentos/<tag>/.

  .venv/bin/python -m src.experimentos.avaliacao_pipeline --rotulos data/rotulos_opus.tsv
  .venv/bin/python -m src.experimentos.avaliacao_pipeline --rotulos data/rotulos_opus.tsv \
      --comparar outputs/amostra_rotulagem.csv
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from src.config import OUT, ROOT
from src.eval import carregar_rotulos
from src.temas import Arvore


def _carrega_candidatos():
    p = OUT / "candidatos.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _resumo(rotulos, publicacao, comparar, tag):
    arv = Arvore()
    rdf, col = carregar_rotulos(rotulos)
    rotmap = dict(zip(rdf.id, rdf[col]))
    extra = rdf.set_index("id").to_dict("index")
    pub = pd.read_csv(ROOT / publicacao, dtype=str).fillna("").set_index("id")
    cands = _carrega_candidatos()

    linhas = []
    for i in rdf.id:
        if i not in pub.index:
            continue
        dec = pub.loc[i, "decisao"]
        tema = pub.loc[i, "tema_central_id"]
        ref = rotmap[i]
        alts = [a for a in [extra[i].get("alternativo", "")] if a]
        aceit = {ref} | set(alts)
        C = cands.get(i, {}).get("candidatos", [])
        linhas.append(
            {
                "id": i,
                "decisao": dec,
                "tema_publicado": tema,
                "tema_correto": ref,
                "alternativo": ";".join(alts),
                "exato": tema == ref,
                "hier": bool(tema) and arv.relacionado(tema, ref),
                "leniente": bool(tema) and any(arv.relacionado(tema, a) for a in aceit),
                "escolha_de_gemeo": bool(tema) and arv.titulo.get(tema) == arv.titulo.get(ref)
                and arv.raiz(tema) != arv.raiz(ref),
                "correto_recuperavel": bool(ref) and (ref in C or any(arv.relacionado(ref, c) for c in C)),
                "duvida": extra[i].get("duvida", ""),
                "multitema": extra[i].get("multitema", ""),
            }
        )
    df = pd.DataFrame(linhas)

    pubm = df[df.decisao == "publicar"]
    rev = df[df.decisao == "revisar"]
    fora = df[df.decisao == "fora"]

    res = {
        "rotulos": str(rotulos),
        "publicacao": str(publicacao),
        "n": len(df),
        "decisoes": df.decisao.value_counts().to_dict(),
        "publicadas": {
            "n": len(pubm),
            "exato": round(pubm.exato.mean(), 4) if len(pubm) else None,
            "hier": round(pubm.hier.mean(), 4) if len(pubm) else None,
            "leniente": round(pubm.leniente.mean(), 4) if len(pubm) and pubm.leniente.notna().any() else None,
            "escolhas_de_gemeo": int(pubm.escolha_de_gemeo.sum()),
            "erros_ids": pubm.loc[~pubm.hier, "id"].tolist(),
        },
        "nao_publicadas": {
            "n": len(rev) + len(fora),
            "correto_recuperavel": int((rev.correto_recuperavel | fora.correto_recuperavel).sum()),
            "sugestao_certa": int(
                (rev.hier | fora.hier).sum()
            ),
        },
    }

    if "duvida" in df.columns and (df.duvida != "").any():
        por_d = {}
        for d, g in pubm.groupby("duvida"):
            por_d[d] = {"n": int(len(g)), "hier": round(g.hier.mean(), 4), "exato": round(g.exato.mean(), 4)}
        res["publicadas_por_duvida"] = por_d

    if comparar:
        rdf2, col2 = carregar_rotulos(comparar)
        r2 = dict(zip(rdf2.id, rdf2[col2]))
        com = [i for i in rotmap if i in r2]
        if com:
            eq = sum(rotmap[i] == r2[i] for i in com)
            rel = sum(arv.relacionado(rotmap[i], r2[i]) for i in com)
            res["acordo_com_outra_rotulagem"] = {
                "arquivo": str(comparar),
                "em_comum": len(com),
                "exato": round(eq / len(com), 4),
                "hier": round(rel / len(com), 4),
            }

    tag = tag or Path(str(rotulos)).stem
    EXP = OUT / "experimentos" / tag
    EXP.mkdir(parents=True, exist_ok=True)
    df.to_csv(EXP / "pipeline_por_questao.csv", index=False)
    (EXP / "pipeline_resumo.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res, EXP


def main():
    ap = argparse.ArgumentParser(description="Pipeline congelado x nova rotulagem.")
    ap.add_argument("--rotulos", default="data/rotulos_opus.tsv")
    ap.add_argument("--publicacao", default="publicacao.csv")
    ap.add_argument("--comparar", default="outputs/amostra_rotulagem.csv")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    res, EXP = _resumo(args.rotulos, args.publicacao, args.comparar, args.tag)
    p = res["publicadas"]
    print(f"=== pipeline congelado x {Path(str(args.rotulos)).name} ===")
    print(f"rotuladas casadas: {res['n']} | decisoes: {res['decisoes']}")
    print(f"PUBLICADAS n={p['n']}: exato={p['exato']} hier={p['hier']} "
          f"leniente={p['leniente']} gemeos={p['escolhas_de_gemeo']}")
    npu = res["nao_publicadas"]
    print(f"NAO publicadas n={npu['n']}: tema correto recuperavel={npu['correto_recuperavel']} "
          f"| sugestao ja certa={npu['sugestao_certa']}")
    if "publicadas_por_duvida" in res:
        print("por duvida:", res["publicadas_por_duvida"])
    if "acordo_com_outra_rotulagem" in res:
        print("acordo com rotulagem antiga:", res["acordo_com_outra_rotulagem"])
    print(f"escrito: {EXP}/pipeline_resumo.json, pipeline_por_questao.csv")


if __name__ == "__main__":
    main()
