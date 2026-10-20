"""Snapshot offline de TODAS as metricas atuais, num so lugar (sem API).

Motivo: antes de qualquer experimento que gaste API (ou mude candidatos), congelar um
retrato reprodutivel do que ja medimos — hashes dos insumos, decisoes, concordancia nas
duas rotulagens, varredura de recuperacao, custo e o plano do A/B.

Nao altera nada. Le arquivos ja existentes e escreve so em
outputs/experimentos/baseline_snapshot/.

  .venv/bin/python -m src.experimentos.snapshot_metricas
"""
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from src.config import OUT, ROOT

EXP = OUT / "experimentos" / "baseline_snapshot"

INSUMOS = [
    ROOT / "publicacao.csv",
    OUT / "candidatos.json",
    OUT / "votos.jsonl",
    OUT / "votos_verificacao.jsonl",
    OUT / "questoes_limpas.csv",
    ROOT / "data" / "temas.csv",
    ROOT / "data" / "dicionario_juridico.csv",
    OUT / "amostra_rotulagem.csv",
    ROOT / "data" / "rotulos_opus.tsv",
]


def _hash(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError:
        return None


def _json(p):
    try:
        return json.loads(open(p, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return None


def coletar():
    snap = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hashes": {str(p.relative_to(ROOT)): _hash(p) for p in INSUMOS},
        "decisoes": None,
        "concordancia": {},
        "recuperacao": {},
        "custo": _json(OUT / "uso.json"),
        "ab_juiz_plano": {
            "antigos_93": _json(OUT / "experimentos" / "ab_juiz" / "plano.json"),
            "opus_148": _json(OUT / "experimentos" / "ab_juiz" / "plano_rotulos_opus.json"),
        },
    }

    pub = ROOT / "publicacao.csv"
    if pub.exists():
        d = pd.read_csv(pub, dtype=str).fillna("")
        snap["decisoes"] = d["decisao"].value_counts().to_dict()

    for tag in ("rotulos_opus", "amostra_deepseek"):
        r = _json(OUT / "experimentos" / tag / "pipeline_resumo.json")
        if r:
            snap["concordancia"][tag] = r

    for arq, chave in ((OUT / "avaliacao" / "registro.csv", "antigos_93"),
                       (OUT / "avaliacao" / "registro_rotulos_opus.csv", "opus_148")):
        if arq.exists():
            d = pd.read_csv(arq)
            g = d.groupby("config").last()
            snap["recuperacao"][chave] = {
                cfg: {
                    "n": int(row.n),
                    "recall_exato": round(float(row.recall_exato), 4),
                    "recall_hier": round(float(row.recall_hier), 4),
                    "cands_media": round(float(row.cands_media), 1),
                }
                for cfg, row in g.iterrows()
            }
    return snap


def markdown(s):
    L = []
    L.append("# Snapshot das metricas atuais")
    L.append("")
    L.append(f"Gerado em {s['gerado_em']} (offline, sem API). Congela o estado **antes** do")
    L.append("experimento de dicionario no retrieval. Fonte dos numeros: `outputs/`.")
    L.append("")
    L.append("## Decisoes da entrega (`publicacao.csv`)")
    L.append("")
    if s["decisoes"]:
        tot = sum(s["decisoes"].values())
        for k in ("publicar", "revisar", "fora"):
            v = s["decisoes"].get(k, 0)
            L.append(f"- **{k}**: {v} ({v/tot:.1%})")
    L.append("")
    L.append("## Concordancia do pipeline congelado (as duas rotulagens)")
    L.append("")
    L.append("| rotulagem | publicadas | exato | hier | leniente | Wilson95 (hier) | gemeo |")
    L.append("|---|---|---|---|---|---|---|")
    import math

    def wilson(k, n, z=1.96):
        if n == 0:
            return (0.0, 0.0)
        p = k / n
        d = 1 + z * z / n
        c = (p + z * z / (2 * n)) / d
        h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
        return (max(0, c - h), min(1, c + h))

    for tag, r in s["concordancia"].items():
        p = r["publicadas"]
        n = p["n"]
        lo, hi = wilson(round(p["hier"] * n), n)
        len_ = p.get("leniente")
        L.append(
            f"| {tag} | {n} | {p['exato']} | {p['hier']} | {len_ if len_ is not None else '—'} "
            f"| [{lo:.2f}; {hi:.2f}] | {p['escolhas_de_gemeo']} |"
        )
    L.append("")
    L.append("## Recuperacao (ultimo run por config, k=10)")
    L.append("")
    for chave, cfg in s["recuperacao"].items():
        L.append(f"### {chave}")
        L.append("")
        L.append("| config | n | recall_exato | recall_hier | cands |")
        L.append("|---|---|---|---|---|")
        for c, m in cfg.items():
            L.append(f"| {c} | {m['n']} | {m['recall_exato']} | {m['recall_hier']} | {m['cands_media']} |")
        L.append("")
    L.append("## Plano do A/B (dry-run, gratis) — chamadas novas por config")
    L.append("")
    for chave, plano in s["ab_juiz_plano"].items():
        if not plano:
            continue
        L.append(f"### {chave}")
        L.append("")
        L.append("| config | novas | cache | total | tok_novos~ |")
        L.append("|---|---|---|---|---|")
        for cfg, p in plano["configs"].items():
            L.append(f"| {cfg} | {p['chamadas_novas']} | {p['cache']} | {p['chamadas_total']} | {p['tokens_in_novos']:,.0f} |")
        L.append("")
    L.append("## Hashes dos insumos (reprodutibilidade)")
    L.append("")
    for k, v in s["hashes"].items():
        L.append(f"- `{k}`: `{(v or 'ausente')[:16]}`")
    L.append("")
    return "\n".join(L)


def main():
    s = coletar()
    EXP.mkdir(parents=True, exist_ok=True)
    (EXP / "metricas_atuais.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    (EXP / "metricas_atuais.md").write_text(markdown(s), encoding="utf-8")
    print(f"escrito: {EXP}/metricas_atuais.json")
    print(f"escrito: {EXP}/metricas_atuais.md")


if __name__ == "__main__":
    main()
