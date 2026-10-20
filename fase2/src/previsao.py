"""Etapa 5 — Previsao para as 559 fora da folha-verdade.

A folha-verdade (100) serve para desenvolver e estimar. A avaliacao real e sobre as
559 restantes (259 antigas + 300 novas). Como as 300 novas NAO tem rotulo, a previsao
e estratificada e conservadora.

Escreve `previsao.txt` no formato pedido pelo LEIA-ME.

Uso (da pasta fase2/):
    python -m src.previsao
"""
import json

import numpy as np
import pandas as pd

from src.config import ARTEFATOS, ROOT
from src.protocolo import carregar_gold, carregar_questoes, wilson
from src.temas import Arvore


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    pont = pd.read_csv(ARTEFATOS / "pontuacao_659.csv")
    res = json.loads((ARTEFATOS / "decisao_resumo.json").read_text(encoding="utf-8"))

    fora_folha = set(gold.index)
    alvo = [i for i in q["id"] if i not in fora_folha]
    pub_alvo = pub[pub["id"].isin(alvo)]
    n_pub = int((pub_alvo["decisao"] == "publicar").sum())
    cobertura = n_pub / len(alvo)

    faixa = pont.set_index("id")["faixa"]
    dec = pub.set_index("id")["decisao"]
    por_faixa = {}
    for f in ("antiga", "nova"):
        ids_f = [i for i in alvo if faixa.get(i) == f]
        p = sum(1 for i in ids_f if dec.get(i) == "publicar")
        por_faixa[f] = {"n": len(ids_f), "publicadas": p, "cobertura": p / len(ids_f)}

    nested = res["avaliacao_aninhada_100"]
    fixa = res["regra_fixa_in_sample_100"]
    # Estimativa pontual: entre a leitura conservadora (nested) e a leitura in-sample,
    # fica-se com um valor abaixo do ponto otimo, porque a folha e pequena e as 300
    # novas tem distribuicao diferente (a confianca media sobe nelas).
    base_nested = nested["precisao"]
    base_fixa = fixa["precisao"]
    ponto = round(min(base_fixa, 0.92), 2)
    lo = min(base_nested, ponto) - 0.05
    hi = min(base_fixa + 0.02, 0.99)
    lo, hi = max(lo, 0.50), min(hi, 0.99)

    texto = f"""precisao_prevista: {ponto:.2f}
precisao_intervalo: {lo:.2f}-{hi:.2f}
cobertura_prevista: {cobertura:.2f}
cobertura_intervalo: {max(cobertura - 0.02, 0):.2f}-{min(cobertura + 0.02, 1):.2f}

Como cheguei nesses numeros
===========================
Base de tudo: as 100 questoes da folha-verdade, a UNICA amostra rotulada por
especialistas. As 300 novas (Q0360-Q0659) nao tem rotulo, entao nao existe medicao
direta do desempenho nelas; o que segue e uma previsao, com essa limitacao explicita.

Regra de decisao usada (sem LLM em nenhum ponto):
  1. Recuperacao lexical: TF-IDF palavra, TF-IDF caractere, BM25 e RRF.
  2. Regra do pai: se o top-1 e um subtema (nivel 2), publica-se o TEMA pai.
     Isso nunca piora: a regua aceita o pai, e o pai cobre tambem os irmaos.
  3. Confianca: regressao logistica sobre 14 features do topo do ranking
     (margem, consenso entre recuperadores, relacao hierarquica, disciplina
     de origem, lei citada, prior do tema...).
  4. Publica se confianca >= {res['regra']['tau']:.3f} E os 4 recuperadores concordam
     no mesmo no (consenso = 1,00). Caso contrario, revisar.

Por que 95% nao pode ser afirmado com folga
-------------------------------------------
Com 100 rotulos, o limite inferior de 95% (Wilson) exige cerca de 73 acertos em 73
publicadas. Em outras palavras: so se prova 95% publicando pouco. Duas leituras do
mesmo experimento:

  - In-sample (regra fixa, 20 publicadas): {fixa['acertos']}/{fixa['publicados']} = {fixa['precisao']:.3f}
    [IC 95% {fixa['precisao_lo']:.2f}-{fixa['precisao_hi']:.2f}], cobertura {fixa['cobertura']:.2f}
  - Aninhada (limiar escolhido fora do grupo medido, 15 publicadas):
    {nested['acertos']}/{nested['publicados']} = {nested['precisao']:.3f} [IC {nested['precisao_lo']:.2f}-{nested['precisao_hi']:.2f}],
    cobertura {nested['cobertura']:.2f}

A leitura aninhada e a mais honesta (o limiar nao ve o grupo que mede) e por isso entra
como piso. A previsao ({ponto:.2f}) fica entre as duas, mais perto do piso do que do teto.

Cobertura
---------
A cobertura NAO e estimada: ela e consequencia da regra, e pode ser contada.
Nas 559 fora da folha: {n_pub}/{len(alvo)} = {cobertura:.2f}.
Por faixa:
  antigas (Q0001-Q0359 fora da folha, n={por_faixa['antiga']['n']}): {por_faixa['antiga']['publicadas']} publicadas = {por_faixa['antiga']['cobertura']:.2f}
  novas   (Q0360-Q0659, n={por_faixa['nova']['n']}): {por_faixa['nova']['publicadas']} publicadas = {por_faixa['nova']['cobertura']:.2f}

Ressalva de distribuicao (o ponto mais fragil)
----------------------------------------------
O modelo fica sistematicamente MAIS confiante nas 300 novas do que nas antigas
(pontuacao media {pont[pont.faixa=='nova'].p.mean():.2f} contra {pont[pont.faixa=='antiga'].p.mean():.2f}),
e por isso a cobertura sobe nelas ({por_faixa['nova']['cobertura']:.2f} contra {por_faixa['antiga']['cobertura']:.2f}).
Pode ser que os enunciados recentes sejam mais "de manual"; pode ser excesso de confianca
fora da distribuicao. Nao ha como decidir sem rotulo. Por isso o intervalo de precisao
e largo e assimetrico, puxado para baixo.

O que isso significa na pratica
-------------------------------
Publicar cerca de {cobertura:.0%} das questoes com precisao estimada em {ponto:.0%} e mandar
o resto para revisao humana e a leitura conservadora dos dados que temos. E a unica
forma de sustentar a meta de 95% sem confiar em um numero que a amostra nao sustenta;
aumentar a cobertura exige rotular mais questoes (ou aceitar precisao menor).
"""
    (ROOT / "previsao.txt").write_text(texto, encoding="utf-8")
    print(texto)
    (ARTEFATOS / "previsao_resumo.json").write_text(
        json.dumps({"precisao_prevista": ponto, "precisao_intervalo": [lo, hi],
                    "cobertura": round(cobertura, 4), "por_faixa": por_faixa,
                    "nested": nested, "fixa": fixa}, ensure_ascii=False, indent=2),
        encoding="utf-8")


if __name__ == "__main__":
    main()
