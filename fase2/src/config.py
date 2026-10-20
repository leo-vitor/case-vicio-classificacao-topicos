"""Configuracao da Fase 2 (case novo). Sem LLM: tudo aqui e offline e deterministico.

Diferente da Fase 1, a Fase 2 nao depende de API nenhuma. Caminhos, semente e
parametros ficam centralizados para que qualquer numero do relatorio possa ser
reproduzido a partir dos anexos.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # fase2/
DATA = ROOT / "data"
ARTEFATOS = ROOT / "artefatos"
REPORT = ROOT / "report"

for _d in (ARTEFATOS, REPORT):
    _d.mkdir(parents=True, exist_ok=True)

# Reproducibilidade
SEED = 42

# Recuperacao
TOP_K = 10          # candidatos por questao nas metricas de recall
RRF_K = 60          # constante do Reciprocal Rank Fusion
MAX_FEATURES = 300_000

# Decisao seletiva
ALVO_PRECISAO = 0.95          # meta do case: precisao nas publicadas
Z_CONFIANCA = 1.959964        # 95%
N_SPLITS = 5                  # folds da validacao cruzada
N_REPEATS = 5                 # repeticoes (folds compartilhados entre metodos)
LIMIAR_DUPLICATA = 0.95       # cosine acima disso = near-duplicate (agrupar no mesmo fold)

# Faixas de origem das questoes (Q0001-Q0359 antigas; Q0360-Q0659 novas)
CORTE_FAIXA = 359
