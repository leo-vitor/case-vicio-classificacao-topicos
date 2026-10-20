"""Classificador treinado offline (TF-IDF + regressao logistica) como alternativa barata ao juiz.

O que ele responde: um modelo supervisionado treinado nos rotulos que temos preve o tema
e devolve uma **probabilidade**. Serve para (a) ser piso de comparacao ao juiz de fronteira
e (b) triagem: publicar o facil, mandar o dificil ao LLM.

LIMITACAO CENTRAL (dita em voz alta): poucos rotulos para muitas classes; muitas classes
tem UM exemplo. Por isso:
  - avaliamos por validacao cruzada (k-fold) e, quando pedido, por **generalizacao entre
    rotulagens** (treina numa, testa na outra);
  - reportamos acerto HIERARQUICO top-k (regua do case: tema, pai ou filho), nao so exato;
  - o numero NAO escolhe arquitetura definitiva; e piso de comparacao;
  - calibracao e "cobertura a precisao fixa" indicam se da para TRIAR sem o LLM.

Uso (offline, sem API):
  .venv/bin/python -m src.experimentos.classificador                          # CV nos 93 rotulos (padrao)
  .venv/bin/python -m src.experimentos.classificador --rotulos data/rotulos_opus.tsv
  .venv/bin/python -m src.experimentos.classificador --cruzado                # treina num, testa no outro
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from src.config import OUT
from src.eval import carregar_rotulos
from src.recuperacao import texto_questao
from src.temas import Arvore

TOPS = (1, 3, 5, 10)
SEED = 42
ROTULOS_PADRAO = OUT / "amostra_rotulagem.csv"


def _dados(rotulos):
    """(ids, textos, y) casando questoes limpas com os rotulos pedidos."""
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    rdf, col = carregar_rotulos(rotulos)
    rotmap = {r.id: getattr(r, col) for r in rdf.itertuples() if getattr(r, col)}
    ids = [i for i in q.id if i in rotmap]
    textos = [texto_questao(q.loc[i]) for i in ids]
    y = [rotmap[i] for i in ids]
    return ids, textos, y


def _vetor():
    return TfidfVectorizer(
        strip_accents="unicode", lowercase=True, ngram_range=(1, 2), sublinear_tf=True, min_df=1
    )


def _modelo():
    # regressao logistica -> probabilidades (nao so ranking). "balanced" ajuda com classes raras.
    return LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced", random_state=SEED)


def _topk_acc(arv, y_true, ordem, tops=TOPS):
    ex = {t: 0 for t in tops}
    hi = {t: 0 for t in tops}
    for yt, od in zip(y_true, ordem):
        for t in tops:
            top = od[:t]
            if yt in top:
                ex[t] += 1
            if any(arv.relacionado(yt, c) for c in top):
                hi[t] += 1
    return ex, hi


def _cv(arv, textos, y, k=5, seed=SEED):
    """k-fold embaralhado. Devolve acertos top-k, n, e (pmax, acertou_hier@1) por item."""
    idx = np.arange(len(textos))
    rng = np.random.default_rng(seed)
    rng.shuffle(idx)
    folds = [f for f in np.array_split(idx, k) if len(f)]
    ordem_teste, y_teste, probs = [], [], []
    for f in folds:
        tr = np.setdiff1d(idx, f, assume_unique=False)
        vec = _vetor().fit([textos[i] for i in tr])
        clf = _modelo().fit(vec.transform([textos[i] for i in tr]), [y[i] for i in tr])
        P = clf.predict_proba(vec.transform([textos[i] for i in f]))
        for r, i in enumerate(f):
            ordem = list(clf.classes_[np.argsort(-P[r])])
            ordem_teste.append(ordem)
            y_teste.append(y[i])
            probs.append((float(P[r].max()), bool(any(arv.relacionado(y[i], c) for c in ordem[:1]))))
    ex, hi = _topk_acc(arv, y_teste, ordem_teste)
    return ex, hi, len(y_teste), probs


def _tabela(ex, hi, n):
    print("   k    exato     hier")
    for t in TOPS:
        print(f"   {t:<4} {ex[t]/n:.3f}     {hi[t]/n:.3f}")


def _calibracao(probs):
    """A escala da probabilidade e honesta? E o ranking (quem e mais confiante) ordena bem?

    Nota: com 67-106 classes, a softmax fica sub-dispersa (max ~0,03). Por isso a
    triagem util e por RANKING, nao por limiar absoluto.
    """
    corr = [p for p, ok in probs if ok]
    errados = [p for p, ok in probs if not ok]
    if corr and errados:
        print(f"  prob media quando ACERTA: {np.mean(corr):.3f} | quando ERRA: {np.mean(errados):.3f}")
    ordenado = sorted(probs, key=lambda x: -x[0])
    n = len(ordenado)
    passo = max(1, n // 10)
    print("  decil (1 = mais confiante) | n | acerto hier@1")
    linhas = []
    for d in range(0, n, passo):
        g = ordenado[d:d + passo]
        if not g:
            continue
        acc = sum(ok for _, ok in g) / len(g)
        pm = float(np.mean([p for p, _ in g]))
        linhas.append({"decil": d // passo + 1, "n": len(g), "acerto": round(acc, 3), "prob_media": round(pm, 4)})
        print(f"   {d // passo + 1:2d} | {len(g):3d} | {acc:.3f}")
    return linhas


def _cobertura_precisao(probs):
    """Precisao a cobertura fixa: publicando so os X% mais confiantes, qual a precisao?"""
    ordenado = sorted(probs, key=lambda x: -x[0])
    n = len(ordenado)
    print("  cobertura (top-X% por confianca) | n | precisao hier@1")
    linhas = []
    for cob in (0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
        k = max(1, int(round(cob * n)))
        g = ordenado[:k]
        prec = sum(ok for _, ok in g) / len(g)
        linhas.append({"cobertura": cob, "n": k, "precisao": round(prec, 3)})
        print(f"   {cob * 100:4.0f}% | {k:3d} | {prec:.3f}")
    return linhas


def _cruzado(arv, treino, teste):
    """Generalizacao entre rotulagens: treina num arquivo, testa no outro."""
    _, txt_tr, y_tr = _dados(treino)
    ids_te, txt_te, y_te = _dados(teste)
    vec = _vetor().fit(txt_tr)
    clf = _modelo().fit(vec.transform(txt_tr), y_tr)
    P = clf.predict_proba(vec.transform(txt_te))
    ordem = [list(clf.classes_[np.argsort(-P[r])]) for r in range(len(ids_te))]
    ex, hi = _topk_acc(arv, y_te, ordem)
    print(f"\n[TREINA {Path(str(treino)).name} -> TESTA {Path(str(teste)).name}] n={len(ids_te)} "
          f"| classes no treino={len(set(y_tr))}")
    _tabela(ex, hi, len(ids_te))
    return {"treino": str(treino), "teste": str(teste), "n": len(ids_te),
            "exato": {str(t): ex[t] / len(ids_te) for t in TOPS},
            "hier": {str(t): hi[t] / len(ids_te) for t in TOPS}}


def _analisa(arv, rotulos, k=5):
    ids, textos, y = _dados(rotulos)
    n_classes = len(set(y))
    sing = sum(1 for t in set(y) if y.count(t) == 1)
    print(f"=== {Path(str(rotulos)).name} | n={len(ids)} rotulos | {n_classes} classes | "
          f"{sing} singletons ({sing/n_classes:.0%}) ===")
    ex, hi, n, probs = _cv(arv, textos, y, k=k)
    print("[validacao cruzada, k=%d] acerto pela regua do case:" % k)
    _tabela(ex, hi, n)
    print("\n[calibracao] probabilidade vs acerto real (hier@1):")
    cal = _calibracao(probs)
    print("\n[precisao a cobertura fixa] (triagem por confianca; e o que importa p/ decidir sem LLM):")
    cob = _cobertura_precisao(probs)
    return {
        "rotulos": str(rotulos), "n": len(ids), "classes": n_classes, "singletons": sing,
        "cv_exato": {str(t): ex[t] / n for t in TOPS},
        "cv_hier": {str(t): hi[t] / n for t in TOPS},
        "calibracao": cal, "cobertura_precisao": cob,
    }


def main():
    ap = argparse.ArgumentParser(description="Classificador treinado offline (TF-IDF + logreg).")
    ap.add_argument("--rotulos", default=str(ROTULOS_PADRAO), help="arquivo de rotulos (CSV/TSV)")
    ap.add_argument("--k", type=int, default=5, help="folds da validacao cruzada")
    ap.add_argument("--cruzado", action="store_true", help="treina numa rotulagem, testa na outra")
    ap.add_argument("--out", default="classificador", help="tag em outputs/experimentos/")
    args = ap.parse_args()

    arv = Arvore()
    res = _analisa(arv, args.rotulos, k=args.k)

    if args.cruzado:
        pares = [(str(ROTULOS_PADRAO), "data/rotulos_opus.tsv"), ("data/rotulos_opus.tsv", str(ROTULOS_PADRAO))]
        res["cruzado"] = [_cruzado(arv, tr, te) for tr, te in pares]

    EXP = OUT / "experimentos" / args.out
    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / "classificador_resumo.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nescrito: {EXP}/classificador_resumo.json")


if __name__ == "__main__":
    main()
