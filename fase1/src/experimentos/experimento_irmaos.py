"""Experimento offline: a expansao por IRMAOS vale a pena?

Compara configuracoes de recuperacao nas 93 questoes rotuladas medindo, de uma vez,
as TRES coisas que importam para a decisao:

  1. GANHO de recuperacao   -> recall_exato / recall_hier / cands_media
                              (reusa o nucleo canonico de src.recuperacao)
  2. RISCO de confusao por GEMEO -> quantas questoes ficam com o GEMEO DO TEMA CORRETO
                              na lista (mesmo titulo, raiz diferente) e quantas ficam
                              com o tema correto E o seu gemeo juntos (a pior confusao)
  3. CUSTO extra de julgar  -> tamanho do bloco de candidatos (o UNICO trecho do prompt
                              que muda entre configuracoes) e o delta de tokens por questao

Tudo offline, sem API, em segundos. NAO altera o pipeline entregue
(`publicacao.csv` permanece 222/136/1).

  .venv/bin/python -m src.experimentos.experimento_irmaos            # conjunto 'todos'
  .venv/bin/python -m src.experimentos.experimento_irmaos --conjunto holdout
  .venv/bin/python -m src.experimentos.experimento_irmaos --rotulos data/rotulos_opus.tsv

Saidas em outputs/experimentos/irmaos/:
  resumo.csv       uma linha por config (metricas + risco + custo)
  por_questao.csv  exposicao por questao x config (auditar caso a caso)
  resumo.json      resumo + metadados (versao dos dados, premissas de custo)

Nota de custo: usamos o MESMO proxy do repo (src/fallback_arvore.py: chars/3). Ele
superestima um pouco (a arvore inteira deu 8.894 no proxy contra 8.446 medidos em
outputs/uso.json), entao os numeros de token aqui sao um TETO, nao uma media.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from src.config import OUT
from src.dicionario import Dicionario
from src.eval import carregar_conjunto, parse_config, versao_dados
from src.recuperacao import (
    avaliar,
    montar_candidatos,
    pool_publicavel,
    ranking,
    texto_questao,
    textos_temas,
)
from src.temas import Arvore

EXP = OUT / "experimentos" / "irmaos"
LEG = "Direito Penal - Legislação Especial"

# Proxy de contagem de tokens do proprio repo (chars // 3). Conservador (teto).
CHARS_POR_TOKEN = 3.0
# Ancora medida para o MEMO (nao usada para estimar token absoluto aqui):
# outputs/uso.json -> media de tokens_in das chamadas novas = 8.446.

CONFIGS = [
    ("tfidf+top", "baseline sem expansao"),
    ("tfidf+filho", "CONFIG ATUAL (entrega)"),
    ("tfidf+top+dic", "dicionario, mantendo a lista em ~10"),
    ("tfidf+filho+dic", "dicionario + filhos"),
    ("tfidf+irmao", "irmaos, sem dicionario"),
    ("tfidf+irmao+dic", "irmaos + dicionario (melhor recall)"),
]


def bloco_chars(arv, ids):
    """Caracteres do bloco '{id} | {caminho}' que vai no prompt do juiz."""
    return sum(len(f"{t} | {arv.caminho[t]}") + 1 for t in ids)


def gemeo_do_correto(arv, C, t):
    """Gemeos do tema correto presentes na lista: mesmo titulo, raiz diferente."""
    titulo, raiz = arv.titulo, arv.raiz
    return [c for c in C if c != t and titulo[c] == titulo[t] and raiz(c) != raiz(t)]


def pares_gemeos(arv, C):
    """Pares (mesmo titulo, raizes diferentes) que coexistem na lista."""
    por_titulo = {}
    for t in C:
        por_titulo.setdefault(arv.titulo[t], []).append(t)
    return sum(1 for v in por_titulo.values() if len(v) > 1 and len({arv.raiz(x) for x in v}) > 1)


def construir(arv, pool, t_texts, q, ids, dic, cfg, k):
    retriever, modo, usa_dic = parse_config(cfg)
    q_texts = [texto_questao(q.loc[i]) for i in ids]
    if usa_dic:
        q_texts = [dic.expandir(t) for t in q_texts]
    ranks, _ = ranking(retriever, q_texts, t_texts)
    return {qid: montar_candidatos(arv, pool, ranks[n], k, modo) for n, qid in enumerate(ids)}


def main():
    args = sys.argv[1:]
    k = int(args[args.index("--k") + 1]) if "--k" in args else 10
    conjunto = args[args.index("--conjunto") + 1] if "--conjunto" in args else "todos"
    rotulos = args[args.index("--rotulos") + 1] if "--rotulos" in args else None
    tag = "_" + Path(rotulos).stem if rotulos else ""

    arv = Arvore()
    q, ids, rotmap = carregar_conjunto(arv, conjunto, rotulos)
    dic = Dicionario()
    pool = pool_publicavel(arv)
    t_texts = textos_temas(arv, pool)
    gemeos_arvore = arv.gemeos()

    linhas, porq = [], []
    for cfg, desc in CONFIGS:
        cands = construir(arv, pool, t_texts, q, ids, dic, cfg, k)
        m = avaliar(arv, ids, cands, rotmap)

        n_gem_correto = n_correto_e_gem = n_par = 0
        for i in ids:
            C, t = cands[i], rotmap[i]
            tw = gemeo_do_correto(arv, C, t)
            if tw:
                n_gem_correto += 1
            if tw and t in C:
                n_correto_e_gem += 1
            n_par += int(pares_gemeos(arv, C) > 0)
            porq.append(
                {
                    "id": i,
                    "config": cfg,
                    "tema_correto_id": t,
                    "tema_correto_e_gemeo": t in gemeos_arvore,
                    "n_candidatos": len(C),
                    "correto_na_lista": t in C,
                    "gemeo_do_correto_na_lista": bool(tw),
                    "correto_e_gemeo_juntos": bool(tw and t in C),
                    "gemeos_do_correto": ";".join(tw),
                }
            )

        chars_cand = bloco_chars(arv, [c for C in cands.values() for c in C]) / len(ids)
        tok_cand = chars_cand / CHARS_POR_TOKEN
        leg = m["por_disciplina"].get(LEG, {"n": 0, "acertos": 0})
        linhas.append(
            {
                "config": cfg,
                "descricao": desc,
                "n": m["n"],
                "recall_exato": round(m["recall_exato"], 4),
                "recall_hier": round(m["recall_hier"], 4),
                "cands_media": round(m["cands_media"], 1),
                "leg_esp": f"{leg['acertos']}/{leg['n']}",
                "n_gemeo_do_correto": n_gem_correto,
                "n_correto_e_gemeo": n_correto_e_gem,
                "n_listas_com_par_gemeo": n_par,
                "chars_candidatos": round(chars_cand),
                "tok_candidatos_teto": round(tok_cand),
            }
        )

    df = pd.DataFrame(linhas)
    base_chars = df.loc[df.config == "tfidf+filho", "chars_candidatos"].iloc[0]
    base_tok = df.loc[df.config == "tfidf+filho", "tok_candidatos_teto"].iloc[0]
    df["lista_x_atual"] = (df["chars_candidatos"] / base_chars).round(2)
    # Delta de tokens de ENTRADA por questao (4 votos) relativo a config atual.
    df["delta_tok_q4"] = ((df["tok_candidatos_teto"] - base_tok) * 4).round(0).astype(int)

    EXP.mkdir(parents=True, exist_ok=True)
    df.to_csv(EXP / f"resumo{tag}_{conjunto}.csv", index=False)
    pd.DataFrame(porq).to_csv(EXP / f"por_questao{tag}_{conjunto}.csv", index=False)
    (EXP / f"resumo{tag}_{conjunto}.json").write_text(
        json.dumps(
            {
                "gerado_por": "src/experimento_irmaos.py",
                "conjunto": conjunto,
                "k": k,
                "rotulos": rotulos or "outputs/amostra_rotulagem.csv",
                "dados": versao_dados(rotulos),
                "premissas_custo": {
                    "chars_por_token": CHARS_POR_TOKEN,
                    "observacao": (
                        "custo do juiz: apenas o bloco de candidatos muda entre configs; "
                        "tokens do bloco = chars/3 (proxy do repo). Teto, nao media: a "
                        "arvore inteira deu 8.894 no proxy contra 8.446 medidos."
                    ),
                    "ancora_medida_tokens_in_por_call": 8446,
                },
                "linhas": linhas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    pd.set_option("display.width", 220)
    print(f"=== irmaos: config x risco x custo (k={k}, conjunto={conjunto}, n={len(ids)}) ===")
    print(
        df[
            [
                "config",
                "recall_hier",
                "recall_exato",
                "cands_media",
                "leg_esp",
                "n_gemeo_do_correto",
                "n_correto_e_gemeo",
                "lista_x_atual",
                "delta_tok_q4",
            ]
        ].to_string(index=False)
    )
    print(f"\ntemas gemeos na arvore: {len(gemeos_arvore)} | rotuladas cujo tema correto e gemeo: "
          f"{sum(1 for i in ids if rotmap[i] in gemeos_arvore)}/{len(ids)}")
    print(f"escrito: {EXP}/resumo{tag}_{conjunto}.csv, por_questao{tag}_{conjunto}.csv, resumo{tag}_{conjunto}.json")


if __name__ == "__main__":
    main()
