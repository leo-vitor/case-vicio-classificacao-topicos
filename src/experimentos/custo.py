"""Fase 3: custo observado por etapa e por mil questoes (offline).

Le o que foi MEDIDO (outputs/uso.json do ultimo run do judge; outputs/uso_etapas.jsonl
acumulado) e calcula consumo por 1.000 questoes. Separa claramente:
  - MEDIDO   : tokens/chamadas observados nesta execucao.
  - PROJECAO : extrapolacao para 50 mil questoes/semana (nao medido).

Preco: nao inventamos. Se GEMINI_PRECO_IN_POR_MILHAO / _OUT_ estiverem definidos no
ambiente, calculamos custo; senao, mostramos apenas tokens e marcamos "preco a confirmar".

  python -m src.experimentos.custo
"""
import json
import os

from src.config import OUT
from src.uso import ler as ler_etapas

RUNS_POR_MODELO = int(os.getenv("RUNS_PER_MODEL", "2"))
N_MODELOS = len([m for m in os.getenv("JUDGE_MODELS", "a,b").split(",") if m.strip()])
VOTOS_POR_QUESTAO = RUNS_POR_MODELO * N_MODELOS or 4


def _uso_json():
    p = OUT / "uso.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    uso = _uso_json()
    etapas = ler_etapas()
    pi = os.getenv("GEMINI_PRECO_IN_POR_MILHAO")
    po = os.getenv("GEMINI_PRECO_OUT_POR_MILHAO")

    print("=== MEDIDO (ultimo run do judge, em outputs/uso.json) ===")
    ch = uso.get("chamadas") or 0
    tin, tout = uso.get("tokens_in") or 0, uso.get("tokens_out") or 0
    pens = uso.get("tokens_pensando") or 0
    print(f"  chamadas novas: {ch} | cache: {uso.get('cache')} | questoes no run: "
          f"{ch + (uso.get('cache') or 0)} / {VOTOS_POR_QUESTAO} = {(ch + (uso.get('cache') or 0)) / VOTOS_POR_QUESTAO:.0f}")
    print(f"  tokens in={tin:,} out={tout:,} pensando={pens:,} segundos={uso.get('segundos')}")
    if ch:
        print(f"  por chamada: in={tin/ch:,.0f} out={tout/ch:,.0f} pensando={pens/ch:,.0f}")
        print("  ATENCAO: as chamadas novas foram as do fallback (prompt grande);")
        print("           usam media ALTA e superestimam um run tipico.")

    print("\n=== MEDIDO por etapa (outputs/uso_etapas.jsonl; null = nao medido) ===")
    if not etapas:
        print("  (vazio) As etapas antigas nao gravavam; a instrumentacao vale das proximas execucoes.")
    for r in etapas:
        print(f"  {r['quando']} {r['etapa']}: in={r.get('tokens_in')} out={r.get('tokens_out')} "
              f"chamadas={r.get('chamadas')} seg={r.get('segundos')} {r.get('observacao','')}")

    print("\n=== PROJECAO para 1.000 e 50.000 questoes (rotulada como projecao) ===")
    if ch:
        in_por_q = (tin / ch) * VOTOS_POR_QUESTAO
        out_por_q = (tout / ch) * VOTOS_POR_QUESTAO
        for n in (1000, 50000):
            print(f"  {n:>6} questoes: in~{in_por_q*n/1e6:,.1f}M  out~{out_por_q*n/1e6:,.2f}M tokens")
        print("  (50 mil/semana = volume do case; e a mesma conta multiplicada)")
    else:
        print("  sem chamadas medidas; nao projeta.")

    print("\n=== CUSTO ===")
    if pi and ch:
        custo_q = ((tin / ch) * VOTOS_POR_QUESTAO / 1e6) * float(pi) + ((tout / ch) * VOTOS_POR_QUESTAO / 1e6) * float(po or 0)
        print(f"  com preco informado (in=US${pi}/M, out=US${po}/M): ~US$ {custo_q:.4f} por questao "
              f"| US$ {custo_q*1000:.2f} por 1.000")
    else:
        print("  Preco nao informado. Defina GEMINI_PRECO_IN_POR_MILHAO e _OUT_ para calcular.")
        print("  (Nao estimamos preco: o valor depende do contrato/tabela vigente.)")


if __name__ == "__main__":
    main()
