"""Etapa 1: limpa o HTML e monta o texto de cada questao."""
import html
import json
import re
import pandas as pd
from src.config import DATA, OUT


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


def load_questoes(path=None):
    rows = []
    with open(path or DATA / "questoes.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def montar(q):
    alts = q.get("alternativas") or {}
    alt_txt = "\n".join(f"{k}) {strip_html(str(v))}" for k, v in alts.items())
    partes = [strip_html(q.get("enunciado_html")), strip_html(q.get("comando")), alt_txt]
    return "\n".join(p for p in partes if p).strip()


def main():
    rows = load_questoes()
    df = pd.DataFrame(
        {
            "id": [q["id"] for q in rows],
            "texto": [montar(q) for q in rows],
            "disciplina_origem": [q.get("disciplina_origem") or "" for q in rows],
            "assunto_origem": [q.get("assunto_origem") or "" for q in rows],
        }
    )
    vazias = (df["texto"].str.len() < 15).sum()
    df.to_csv(OUT / "questoes_limpas.csv", index=False)
    print(f"{len(df)} questoes limpas. Textos muito curtos (<15 chars): {vazias}")


if __name__ == "__main__":
    main()
