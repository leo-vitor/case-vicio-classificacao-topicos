"""Aplica em src/decide.py a leitura de outputs/votos_verificacao.jsonl (voto extra do verificador).

Uso, na raiz do repositorio:  python aplicar_verificador.py
Faz backup em src/decide.py.bak, e e seguro rodar de novo (nao duplica).
"""
import re
import shutil
import sys
from pathlib import Path

p = Path("src/decide.py")
s = p.read_text(encoding="utf-8")
if "votos_verificacao" in s:
    print("Ja aplicado: src/decide.py ja le votos_verificacao.jsonl.")
    sys.exit(0)

m1 = re.search(r'^([ \t]*)with open\(OUT / "votos\.jsonl", encoding="utf-8"\) as (\w+):\s*$', s, flags=re.M)
if not m1:
    sys.exit('Nao achei a linha: with open(OUT / "votos.jsonl", encoding="utf-8") as f:  (me mande o src/decide.py)')
ind = m1.group(1)
bloco = (
    f'{ind}ver = {{}}\n'
    f'{ind}vp = OUT / "votos_verificacao.jsonl"\n'
    f'{ind}if vp.exists():\n'
    f'{ind}    with open(vp, encoding="utf-8") as fv:\n'
    f'{ind}        for lv in fv:\n'
    f'{ind}            x = json.loads(lv)\n'
    f'{ind}            ver[x["id"]] = x["vote"]\n'
)
s2 = s[: m1.start()] + bloco + s[m1.start():]
m2 = re.search(r'^([ \t]*)(\w+) = json\.loads\(line\)\s*$', s2[m1.start() + len(bloco):], flags=re.M)
if not m2:
    sys.exit("Nao achei a linha: r = json.loads(line)  (me mande o src/decide.py)")
ind2, var = m2.group(1), m2.group(2)
pos = m1.start() + len(bloco) + m2.end()
add = (
    f'\n{ind2}if {var}["id"] in ver:\n'
    f'{ind2}    {var}["votes"] = {var}["votes"] + [ver[{var}["id"]]]'
)
s3 = s2[:pos] + add + s2[pos:]
shutil.copy(p, "src/decide.py.bak")
p.write_text(s3, encoding="utf-8")
print("Aplicado. Backup em src/decide.py.bak. Rode: python -m src.decide")
