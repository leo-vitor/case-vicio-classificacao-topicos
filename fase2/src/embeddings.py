"""Etapa 2 — Embeddings densos locais (offline, versionados).

O TF-IDF saturou: o tema certo (ou a ramificação certa) só aparece em ~59% dos
top-1. Embeddings multilíngues capturam paráfrase e sinônimo que o léxico não vê.

Regras respeitadas aqui:
  - modelo LOCAL (nenhuma API na execução);
  - vetores gravados em disco com nome que inclui modelo, dimensão e hash dos textos;
  - a execução final pode rodar sem rede: só recomputa se o cache não existir.

Uso:
    python -m src.embeddings --modelo intfloat/multilingual-e5-large
"""
import argparse
import hashlib

import numpy as np

from src.config import ARTEFATOS, DATA
from src.clean import quadro
from src.protocolo import carregar_gold, carregar_questoes
from src.recuperacao import texto_questao, texto_tema
from src.temas import Arvore

MODELO_PADRAO = "intfloat/multilingual-e5-large"


def _hash(textos):
    h = hashlib.sha256("\n".join(textos).encode("utf-8")).hexdigest()[:12]
    return h


def _cache(modelo, nome, textos, prefixo):
    chave = f"{modelo.replace('/', '_')}_{nome}_{_hash(textos)}.npy"
    p = ARTEFATOS / "emb" / chave
    if p.exists():
        return np.load(p)
    return None


def _gravar(modelo, nome, textos, prefixo, vetores):
    d = ARTEFATOS / "emb"
    d.mkdir(parents=True, exist_ok=True)
    chave = f"{modelo.replace('/', '_')}_{nome}_{_hash(textos)}.npy"
    np.save(d / chave, vetores)
    (d / f"{chave}.txt").write_text(
        f"modelo: {modelo}\nnome: {nome}\nprefixo: {prefixo}\nn: {len(textos)}\n"
        f"dim: {vetores.shape[1]}\nhash_textos: {_hash(textos)}\n",
        encoding="utf-8",
    )
    return vetores


def codificar(modelo, nome, textos, prefixo="", batch=32):
    """Codifica com cache em disco. Para e5, o prefixo ('query: '/'passage: ') importa."""
    cache = _cache(modelo, nome, textos, prefixo)
    if cache is not None:
        return cache
    from sentence_transformers import SentenceTransformer

    st = SentenceTransformer(modelo, device="mps")
    entradas = [prefixo + t for t in textos] if prefixo else textos
    v = st.encode(entradas, batch_size=batch, convert_to_numpy=True,
                  normalize_embeddings=True, show_progress_bar=False)
    return _gravar(modelo, nome, textos, prefixo, v.astype("float32"))


def matriz_similaridade(modelo=MODELO_PADRAO):
    """Similaridade questao x tema (371), cosseno, vetores normalizados."""
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    qmap = q.set_index("id")
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    t_textos = [texto_tema(arv, t) for t in pool]
    q_textos = [texto_questao(qmap.loc[i]) for i in gold.index]

    pref_q = "query: " if "e5" in modelo else ""
    pref_t = "passage: " if "e5" in modelo else ""
    Vt = codificar(modelo, "temas", t_textos, pref_t)
    Vq = codificar(modelo, "questoes100", q_textos, pref_q)
    return Vq @ Vt.T, pool, list(gold.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default=MODELO_PADRAO)
    args = ap.parse_args()
    M, pool, ids = matriz_similaridade(args.modelo)
    print(f"{args.modelo}: matriz {M.shape} (questoes x temas publicaveis)")


if __name__ == "__main__":
    main()
