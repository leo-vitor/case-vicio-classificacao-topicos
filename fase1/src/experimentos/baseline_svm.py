"""Fase 3: baseline supervisionado simples (TF-IDF + SVM linear), offline.

Pergunta que ele responde: um classificador linear barato, treinado nos rotulos que
temos, chega perto do juiz de fronteira? Serve de piso de comparacao e de argumento de
custo (roda local, sem API).

LIMITACAO CENTRAL (dita em voz alta): temos 93 rotulos para ~70+ classes. Muitas classes
tem UM exemplo — impossivel aprender/avaliar de forma estavel. Por isso:
  - usamos validacao leave-one-out (treina em 92, testa em 1);
  - reportamos acerto hierarquico top-k (a regua do case: tema, pai ou filho), nao
    acerto exato de 1 classe, que seria artificialmente baixo;
  - o resultado NAO deve escolher arquitetura definitiva; e indicativo.

  python -m src.experimentos.baseline_svm
"""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC

from src.config import OUT
from src.recuperacao import texto_questao
from src.temas import Arvore

TOPS = (1, 3, 5, 10)


def main():
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    rot = pd.read_csv(OUT / "amostra_rotulagem.csv", dtype=str).fillna("")
    rot = rot[rot["tema_correto_id"] != ""]
    ids = [i for i in q.id if i in set(rot.id)]
    y = np.array([rot.set_index("id").loc[i, "tema_correto_id"] for i in ids])
    textos = [texto_questao(q.loc[i]) for i in ids]

    n_classes = len(set(y))
    singletons = sum(1 for t in set(y) if list(y).count(t) == 1)
    print(f"n={len(ids)} rotulos | {n_classes} classes | {singletons} classes com 1 exemplo "
          f"({singletons/n_classes:.0%})")
    print("Validacao: leave-one-out. Acerto pela regua do case (tema/pai/filho).\n")

    vec = TfidfVectorizer(strip_accents="unicode", lowercase=True, ngram_range=(1, 2),
                          sublinear_tf=True, min_df=1)
    X = vec.fit_transform(textos)

    acerto_exato = {k: 0 for k in TOPS}
    acerto_hier = {k: 0 for k in TOPS}
    for i in range(len(ids)):
        tr = [j for j in range(len(ids)) if j != i]
        clf = LinearSVC(C=1.0, dual=True, max_iter=5000)
        clf.fit(X[tr], y[tr])
        cl = list(clf.classes_)
        sc = clf.decision_function(X[i])
        ordem = [cl[j] for j in np.argsort(-np.asarray(sc).ravel())]
        for k in TOPS:
            top = ordem[:k]
            if y[i] in top:
                acerto_exato[k] += 1
            if any(arv.relacionado(y[i], c) for c in top):
                acerto_hier[k] += 1

    n = len(ids)
    print("  k   exato     hier")
    for k in TOPS:
        print(f"  {k:<3} {acerto_exato[k]/n:.3f}     {acerto_hier[k]/n:.3f}")

    # piso aleatorio (referencia): prob. de um top-k aleatorio conter algo relacionado
    # = massa media de temas relacionados por questao; aqui aproximamos por disciplina.
    print("\nReferencia: o piso aleatorio de 'acerto hier' e a fracao da arvore relacionada")
    print("ao tema verdadeiro (pequena). O SVM so ajuda se ficar bem acima disso.")


if __name__ == "__main__":
    main()
