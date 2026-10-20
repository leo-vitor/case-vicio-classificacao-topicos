"""Arvore de temas e a regua de acerto do case.

Copiado de `fase1/src/temas.py` (o `temas.csv` e identico entre as fases).

Regua do case (LEIA-ME): publicar no tema central, num extra, ou num PAI ou FILHO
de um deles conta como certo. Irmao (outro subtema do mesmo tema) conta como erro.
Por isso `relacionado` e exatamente: igual, pai direto ou filho direto.
"""
import re

import pandas as pd

from src.config import DATA


class Arvore:
    def __init__(self, path=None):
        df = pd.read_csv(path or DATA / "temas.csv", dtype=str).fillna("")
        df["nivel"] = df["nivel"].astype(int)
        self.df = df
        self.ativos = df[df["status"] == "active"]
        self.parent = {r.tema_id: (r.parent_id or None) for r in df.itertuples()}
        self.nivel = dict(zip(df.tema_id, df.nivel))
        self.caminho = dict(zip(df.tema_id, df.caminho))
        self.titulo = dict(zip(df.tema_id, df.titulo))
        self.ativo = set(self.ativos.tema_id)
        self.nq = {}
        for r in df.itertuples():
            m = re.search(r"(\d+)\s+quest", r.descricao or "")
            self.nq[r.tema_id] = int(m.group(1)) if m else 0
        self.filhos = {}
        for tid, pid in self.parent.items():
            if pid:
                self.filhos.setdefault(pid, []).append(tid)

    def publicavel(self, tid):
        """Raizes (nivel 0) ficam fora: publicar na disciplina inteira nao ajuda o aluno."""
        return tid in self.ativo and self.nivel.get(tid, 0) >= 1

    def relacionado(self, a, b):
        """Regua do case: mesmo no, pai ou filho direto. Irmaos NAO contam."""
        if not a or not b:
            return False
        if a == b:
            return True
        return self.parent.get(a) == b or self.parent.get(b) == a

    def raiz(self, tid):
        return self.caminho.get(tid, "").split(" > ")[0]

    def irmaos(self, tid):
        p = self.parent.get(tid)
        return [c for c in self.filhos.get(p, []) if c != tid] if p else []

    def gemeos(self):
        """Temas com o mesmo titulo em disciplinas diferentes (desambiguacao manual)."""
        df = self.ativos[self.ativos.nivel >= 1]
        g = df.groupby("titulo").filter(
            lambda x: x.caminho.str.split(" > ").str[0].nunique() > 1
        )
        return set(g.tema_id)
