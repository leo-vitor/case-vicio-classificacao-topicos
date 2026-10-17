"""Enriquecimento de consulta por dicionario juridico (Key-Value). Offline, sem API.

Ideia: a busca (TF-IDF/BM25) so encontra um tema se as palavras da questao aparecerem
no texto do tema. Questoes citam referencias ("Lei 11.340", "delacao") que o titulo do
tema nao repete ("Lei Maria da Penha", "Colaboracao Premiada"). O dicionario mapeia essa
referencia para os termos do tema, e esses termos sao adicionados a CONSULTA.

Curadoria manual e deliberadamente pequena (ver docs/dicionario_juridico.md). Nao usamos
LLM para gerar centenas de associacoes: cada linha foi conferida contra os titulos reais
da arvore (data/temas.csv).

Formato de data/dicionario_juridico.csv:
    tipo,chave,termos
    lei,11.340,Lei Maria da Penha violencia domestica
    sinonimo,delacao,Colaboracao Premiada

  - chave : substring procurada no texto da questao (normalizado: minusculo, sem acento)
  - termos: texto acrescentado a consulta quando a chave casa
"""
import hashlib
import unicodedata
from pathlib import Path

import pandas as pd

from src.config import DATA

PADRAO = DATA / "dicionario_juridico.csv"


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


class Dicionario:
    def __init__(self, path=None):
        self.path = Path(path or PADRAO)
        self.entradas = []
        if self.path.exists():
            df = pd.read_csv(self.path, dtype=str).fillna("")
            for r in df.itertuples():
                chave = normalizar(r.chave)
                if not chave:
                    continue
                self.entradas.append(
                    {"tipo": r.tipo, "chave": chave, "termos": r.termos.strip()}
                )

    def versao(self) -> str:
        if not self.path.exists():
            return "vazio"
        return hashlib.sha256(self.path.read_bytes()).hexdigest()[:12]

    def casamentos(self, texto: str):
        """Entradas cujo 'chave' aparece no texto. Devolve os termos (sem repetir)."""
        t = normalizar(texto)
        termos, usadas = [], []
        for e in self.entradas:
            if e["chave"] in t:
                if e["termos"] not in termos:
                    termos.append(e["termos"])
                usadas.append(e["chave"])
        return termos, usadas

    def expandir(self, texto: str) -> str:
        termos, _ = self.casamentos(texto)
        return (texto + " " + " ".join(termos)).strip() if termos else texto


def carregar(path=None) -> Dicionario:
    return Dicionario(path)
