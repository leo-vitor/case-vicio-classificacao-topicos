"""Etapa 2b: segunda passada de candidatos para as questoes que o juiz mandou para 'fora'.
Usa n-gramas de caracteres, que casam variacoes como organizacao/organizacoes e ambiente/ambientais."""
import json

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.candidates import texto_tema
from src.config import OUT, ROOT
from src.temas import Arvore

K2 = 10


def main():
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    ids = set(pub.loc[pub["decisao"] == "fora", "id"])
    pool = [t for t in arv.ativos.tema_id if arv.publicavel(t)]
    q_txt = q["texto"].tolist()
    t_txt = [texto_tema(arv, t) for t in pool]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), strip_accents="unicode", sublinear_tf=True)
    vec.fit(q_txt + t_txt)
    sim = cosine_similarity(vec.transform(q_txt), vec.transform(t_txt))
    cand = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    for i, qid in enumerate(q["id"]):
        if qid in ids:
            novos = [pool[j] for j in np.argsort(-sim[i])[:K2]]
            atuais = cand[qid]["candidatos"]
            cand[qid]["candidatos"] = atuais + [t for t in novos if t not in atuais]
    (OUT / "candidatos.json").write_text(json.dumps(cand, ensure_ascii=False), encoding="utf-8")
    print(f"Candidatos ampliados para {len(ids)} questoes (top {K2}): {sorted(ids)}")


if __name__ == "__main__":
    main()