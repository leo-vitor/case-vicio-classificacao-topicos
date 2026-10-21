#!/usr/bin/env bash
# Regenera os entregaveis da Fase 2 do zero: sem rede e sem LLM na decisao.
#
# Uso (de qualquer lugar):
#   ./scripts/regenerar.sh
#
# Tempo de referencia: ~60 s em um nucleo (medido no clone limpo).
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
INICIO=$SECONDS

for m in clean baseline confianca decisao conformal auditoria previsao; do
    printf '\n== %s\n' "$m"
    "$PY" -m "src.$m"
done

# O manifesto da auditoria inclui o hash do previsao.txt, que so existe depois
# do modulo acima. A segunda passada atualiza o manifesto sem mudar os numeros.
printf '\n== auditoria (manifesto final)\n'
"$PY" -m "src.auditoria"

# Diagnostico e curva final usam os artefatos acima; nao mudam os entregaveis,
# mas deixam os docs reproduziveis a partir do mesmo comando.
for m in diagnostico regra_final; do
    printf '\n== %s\n' "$m"
    "$PY" -m "src.$m"
done

printf '\n== hashes\n'
shasum -a 256 publicacao.csv previsao.txt
printf 'tempo total: %ss\n' "$((SECONDS - INICIO))"
