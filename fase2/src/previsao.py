"""Etapa 5 — Previsao para as 559 fora da folha-verdade.

A folha-verdade (100) serve para desenvolver e estimar. A avaliacao real e sobre as
559 restantes (259 antigas + 300 novas). Como as 300 novas NAO tem rotulo, a previsao
e estratificada e conservadora.

Diferente da versao anterior, a precisao NAO sai mais de uma formula artesanal
(`min(in-sample, 0.92)`, piso `nested - 0.05`, teto `in-sample + 0.02`). Agora:

  - o ponto e o intervalo vem do posterior Beta-Binomial (`protocolo.beta_binomial`),
    que e rastreavel: 19 acertos em 20 publicadas com prior uniforme -> Beta(20, 2);
  - a leitura aninhada CORRIGIDA (limiar escolhido sem ver o grupo medido) entra como
    limite de honestidade, nao como parcela de uma media ponderada a mao;
  - a secao "o que se pode certificar" usa a cota de Clopper-Pearson (`src.conformal`)
    para dizer, sem rodeios, o que 100 rotulos sustentam.

Escreve `previsao.txt` no formato pedido pelo LEIA-ME.

Uso (da pasta fase2/):
    python -m src.previsao
"""
import json

import numpy as np
import pandas as pd

from src.config import ARTEFATOS, ROOT
from src.protocolo import beta_binomial, carregar_gold, carregar_questoes
from src.temas import Arvore


def _ler(p, padrao=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def main():
    arv = Arvore()
    q = carregar_questoes()
    gold = carregar_gold(arv)
    pub = pd.read_csv(ROOT / "publicacao.csv", dtype=str).fillna("")
    pont = pd.read_csv(ARTEFATOS / "pontuacao_659.csv")
    res = json.loads((ARTEFATOS / "decisao_resumo.json").read_text(encoding="utf-8"))
    aud = _ler(ARTEFATOS / "auditoria.json", {})
    conf = _ler(ARTEFATOS / "conformal.json", {})

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
    tau = res["regra"]["tau"]
    consenso = float(res["regra"].get("consenso_min", 1.0))

    # Ponto e intervalo: posterior Beta-Binomial da regra fixa (a que e aplicada).
    post = beta_binomial(fixa["acertos"], fixa["publicados"])
    ponto = round(post["media"], 2)
    lo, hi = round(post["lo"], 2), round(post["hi"], 2)

    # Leitura aninhada corrigida (se a auditoria tiver rodado) e o teto certificavel.
    corr = aud.get("aninhado", {}).get("corrigido_sem_vazamento")
    cert_nested = aud.get("certificado_nested", {})
    cert_insample = {c["alpha_erro"]: c for c in conf.get("certificado", [])}
    cert_alpha = min([a for a in cert_insample if cert_insample[a]["publicados"]], default=None)

    bloco_corr = ""
    if corr:
        bloco_corr = (
            f"  - Aninhada CORRIGIDA (limiar escolhido em probabilidades internas, que nunca\n"
            f"    viram o grupo medido; a versao anterior tinha esse vazamento):\n"
            f"    {corr['acertos']}/{corr['publicados']} = {corr['precisao']:.3f} "
            f"[IC {corr['precisao_lo']:.2f}-{corr['precisao_hi']:.2f}], cobertura {corr['cobertura']:.2f}\n"
        )

    # Nivel aninhado comparavel: menor alpha com pelo menos 10 publicadas.
    cert_n = None
    for a in sorted(cert_nested, key=lambda s: float(s.split("_")[1])):
        c = cert_nested[a]
        if c.get("publicados", 0) >= 10:
            cert_n = c
            break
    frase_nested = (
        f"Na versao aninhada desse mesmo criterio, a certificacao honesta cai para\n"
        f"{cert_n['precisao']:.0%} de precisao ({cert_n['publicados']} publicadas)."
        if cert_n else "A versao aninhada desse criterio nao chega a 10 publicadas."
    )

    bloco_cert = "com 100 rotulos, a amostra NAO sustenta 95% (nem 90%) em nenhuma cobertura."
    if cert_alpha is not None:
        c = cert_insample[cert_alpha]
        bloco_cert = (
            f"Com 100 rotulos, a amostra NAO sustenta 95% nem 90%: nenhuma cobertura tem cota\n"
            f"superior de erro abaixo disso. O primeiro nivel certificavel e {cert_alpha:.0%} de erro,\n"
            f"com {c['publicados']} publicadas e {c['acertos']} acertos (cota superior de erro\n"
            f"{c['cota_superior_erro']:.3f} <= {cert_alpha}). {frase_nested}"
        )

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
  3. Confianca: regressao logistica sobre 13 features do topo do ranking
     (margem, consenso entre recuperadores, relacao hierarquica, disciplina
     de origem, lei citada, prior do tema...).
  4. Publica se confianca >= {tau:.6f} E o consenso entre os 4 recuperadores e
     >= {consenso:.2f} (1,00 = todos concordam; 0,75 = tres de quatro).
     Caso contrario, revisar. Esse limiar e o valor EXATO usado em
     `publicacao.csv`. A confianca publicada e arredondada para 2 casas no CSV,
     entao o valor efetivo usado na decisao e o que esta em `pontuacao_659.csv`.

A precisao prevista ({ponto:.2f}) e a MEDIA do posterior Beta-Binomial, nao um numero
escolhido a mao: {fixa['acertos']} acertos em {fixa['publicados']} publicadas com prior
uniforme Beta(1,1) dao Beta({1 + fixa['acertos']}, {1 + fixa['publicados'] - fixa['acertos']});
a media e {post['media']:.3f} e o intervalo de 95% e [{post['lo']:.2f}, {post['hi']:.2f}].
O intervalo e largo porque {fixa['publicados']} publicadas sao poucas — e esse e o dado,
nao uma escolha.

Tres leituras do mesmo experimento
----------------------------------
  - In-sample (regra fixa, {fixa['publicados']} publicadas): {fixa['acertos']}/{fixa['publicados']} = {fixa['precisao']:.3f}
    [IC 95% de Wilson {fixa['precisao_lo']:.2f}-{fixa['precisao_hi']:.2f}], cobertura {fixa['cobertura']:.2f}
  - Aninhada (limiar escolhido fora do grupo medido): {nested['acertos']}/{nested['publicados']} = {nested['precisao']:.3f},
    cobertura {nested['cobertura']:.2f}
{bloco_corr}
O limiar final foi escolhido de forma conservadora: entre as regras que sustentam 95% com
pelo menos 20 publicadas nos 100, fica-se com a de maior limiar ({tau:.6f}).

O que se pode CERTIFICAR (e o que nao se pode)
----------------------------------------------
{bloco_cert}
Traduzindo: 95% e a meta do case e o ponto estimado, mas nao e um numero que 100 rotulos
provem. O que a amostra prova fica em torno de 80%.

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
fora da distribuicao. Nao ha como decidir sem rotulo.

E a sensibilidade da regua: o acerto da regra final muda bastante conforme a leitura —
literal (regua do case) {aud.get('metrica', [{}])[0].get('literal', float('nan')):.2f},
so o tema exato {aud.get('metrica', [{}])[0].get('estrita', float('nan')):.2f},
mesmo ramo {aud.get('metrica', [{}])[0].get('frouxa', float('nan')):.2f}.
Como o LEIA-ME aceita pai e filho, a leitura literal e a que vale; as outras duas servem
para mostrar quanto do resultado depende da regua.

O que isso significa na pratica
-------------------------------
Publicar cerca de {cobertura:.0%} das questoes com precisao estimada em {ponto:.0%} e mandar
o resto para revisao humana. E a forma de chegar perto da meta de 95% sem afirmar mais do que
a amostra sustenta; aumentar a cobertura, ou provar 95%, exige rotular mais questoes.
"""
    (ROOT / "previsao.txt").write_text(texto, encoding="utf-8")
    print(texto)
    (ARTEFATOS / "previsao_resumo.json").write_text(
        json.dumps({"precisao_prevista": ponto, "precisao_intervalo": [lo, hi],
                    "metodo": "posterior Beta-Binomial (prior Beta(1,1)) da regra fixa",
                    "posterior": post,
                    "cobertura": round(cobertura, 4), "por_faixa": por_faixa,
                    "nested": nested, "fixa": fixa,
                    "aninhado_corrigido": corr,
                    "certificado_nested": cert_nested,
                    "certificado_in_sample": cert_insample},
                   ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
