"""Etapa 2: para cada questao, seleciona os temas candidatos.

Padrao: TF-IDF (gratis, offline). Opcional: embeddings do Gemini (EMBEDDINGS=gemini).
O assunto_origem entra como pista de texto, nao como verdade (pode estar errado).

Variaveis de ambiente opcionais (nao mudam o padrao da entrega):
  RETRIEVAL_DIC=1                     enriquece a CONSULTA com o dicionario juridico
                                      (mesma logica do experimento `+dic` do src.eval)
  CANDIDATOS_OUT=<caminho>            grava a lista em outro arquivo (ex.: variante)

  RETRIEVAL_DIC=1 CANDIDATOS_OUT=outputs/experimentos/dic/candidatos_dic.json \
      .venv/bin/python -m src.candidates
"""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import CACHE, EMBEDDINGS, EMBEDDING_MODEL, OUT, TOP_K
from src.dicionario import Dicionario
from src.temas import Arvore


def usa_dicionario():
    return os.getenv("RETRIEVAL_DIC", "").strip().lower() in ("1", "true", "sim", "yes")


def texto_tema(arv, tid):
    return arv.caminho[tid].replace(">", " ") + " " + arv.titulo[tid]


def _embed_gemini(texts):
    import os
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    key = hashlib.sha256((EMBEDDING_MODEL + "||".join(texts)).encode()).hexdigest()[:24]
    f = CACHE / f"emb_{key}.npy"
    if f.exists():
        return np.load(f)
    vecs = []
    for i in range(0, len(texts), 50):
        resp = client.models.embed_content(model=EMBEDDING_MODEL, contents=texts[i : i + 50])
        vecs.extend([e.values for e in resp.embeddings])
    arr = np.array(vecs, dtype="float32")
    np.save(f, arr)
    return arr


def similaridades(q_texts, t_texts):
    if EMBEDDINGS == "gemini":
        q = _embed_gemini(q_texts)
        t = _embed_gemini(t_texts)
        return cosine_similarity(q, t)
    vec = TfidfVectorizer(
        strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True, min_df=1
    )
    vec.fit(q_texts + t_texts)
    return cosine_similarity(vec.transform(q_texts), vec.transform(t_texts))


def main():
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    t_texts = [texto_tema(arv, t) for t in pool]
    q_texts = (q["texto"] + " " + q["assunto_origem"] + " " + q["assunto_origem"]).tolist()
    com_dic = usa_dicionario()
    if com_dic:
        dic = Dicionario()
        q_texts = [dic.expandir(t) for t in q_texts]
    sim = similaridades(q_texts, t_texts)

    saida = {}
    for i, qid in enumerate(q["id"]):
        ordem = np.argsort(-sim[i])
        top = [pool[j] for j in ordem[:TOP_K]]
        extra = []
        for t in top:  # pais, para o juiz poder escolher o tema mais geral
            p = arv.parent.get(t)
            if p and arv.publicavel(p) and p not in top and p not in extra:
                extra.append(p)
        for t in top[:3]:  # filhos dos 3 primeiros, se forem temas de nivel 1
            if arv.nivel[t] == 1:
                for c in arv.filhos.get(t, []):
                    if arv.publicavel(c) and c not in top and c not in extra:
                        extra.append(c)
        saida[qid] = {
            "candidatos": top + extra,
            "sim_top1": float(sim[i, ordem[0]]),
            "sim_top2": float(sim[i, ordem[1]]),
        }
    destino = Path(os.getenv("CANDIDATOS_OUT", "") or (OUT / "candidatos.json"))
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False)
    tam = np.mean([len(v["candidatos"]) for v in saida.values()])
    tag = EMBEDDINGS + ("+dic" if com_dic else "")
    print(f"Candidatos gerados ({tag}). Media por questao: {tam:.1f} -> {destino}")


if __name__ == "__main__":
    main()
