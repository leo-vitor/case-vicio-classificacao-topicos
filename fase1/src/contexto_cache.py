"""Cache de contexto (Gemini) para o prefixo REPETIDO do prompt: a ARVORE DE TEMAS.

O PROBLEMA
  Duas etapas mandam a arvore inteira (~375 temas) em TODA chamada:
    - `fallback_arvore` (juiz nos casos dificeis);
    - `verificar_arvore` (5o voto, 261 publicadas).
  Esse bloco e IDENTICO em todas as chamadas. Sem cache, paga-se de novo a cada uma.

O QUE E O CACHE DE CONTEXTO
  Um recurso do Gemini em que voce envia uma vez um prefixo grande, recebe um nome de
  cache e o referencia nas chamadas seguintes. O prefixo passa a ser cobrado com
  DESCONTO (token de entrada em cache) e nao precisa ser reenviado -> menos custo e
  latencia. Ha um custo de armazenamento enquanto o cache existe (TTL).

O QUE ISSO EXIGE
  O prefixo tem de vir PRIMEIRO no prompt. O prompt atual poe a questao antes dos
  candidatos; para cachear, reordenamos: [INSTRUCOES + ARVORE] (estatico, cacheado)
  seguido de [ORIGEM + QUESTAO] (variavel). Isso e uma mudanca de prompt -> por isso
  esta etapa e OPT-IN e nao toca o pipeline entregue.

USO (offline por padrao):
  .venv/bin/python -m src.contexto_cache                # --dry-run: plano em tokens (GRATIS)
  .venv/bin/python -m src.contexto_cache --n 1000       # projeta para N questoes
  .venv/bin/python -m src.contexto_cache --criar        # cria o cache de verdade (USA API)
"""
import argparse
import json
import sys

from src.config import OUT, ROOT
from src.temas import Arvore

PROMPT = (ROOT / "prompts" / "judge_prompt.md").read_text(encoding="utf-8")
INSTRUCOES = PROMPT.split("---")[0].strip()


def _todos(arv):
    return [t for t in arv.ativos.tema_id if arv.publicavel(t)]


def montar_prefixo(arv):
    """Bloco ESTATICO (cacheavel): instrucoes + a arvore inteira (id | caminho)."""
    linhas = "\n".join(f"{t} | {arv.caminho[t]}" for t in _todos(arv))
    return f"{INSTRUCOES}\n\nCANDIDATOS (a arvore completa; id | caminho):\n{linhas}"


def montar_sufixo(row):
    """Bloco VARIAVEL por questao (o que muda a cada chamada)."""
    return (
        "---\n"
        f"DISCIPLINA DE ORIGEM: {row['disciplina_origem'] or '(vazio)'}\n"
        f"ASSUNTO DE ORIGEM: {row['assunto_origem'] or '(vazio)'}\n\n"
        f"QUESTAO:\n{row['texto'][:3500]}\n\n"
        "Escolha um id dos CANDIDATOS acima e responda SOMENTE com JSON."
    )


def estimar_tokens(texto):
    """Proxy chars/3, o mesmo do repo (teto, nao media). Sem API."""
    return len(texto) // 3


def _amostra_sufixo():
    import os

    import pandas as pd

    p = OUT / "questoes_limpas.csv"
    if not p.exists():
        return "", 0
    q = pd.read_csv(p, dtype=str).fillna("")
    textos = [montar_sufixo(r) for _, r in q.iterrows()]
    return textos[0], int(sum(estimar_tokens(t) for t in textos) / max(len(textos), 1))


def _n_arvore_inteira():
    """Quantas questoes hoje recebem a arvore inteira (fallback)."""
    p = OUT / "candidatos.json"
    if not p.exists():
        return 0
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
        return sum(1 for v in c.values() if v.get("fallback_arvore_inteira"))
    except Exception:
        return 0


def planejar(arv, n=None, desconto=0.25, preco_in_por_milhao=None, ttl_horas=1.0):
    """Plano em tokens (GRATIS). desconto=0.25 => token em cache custa 25% do normal."""
    prefixo = montar_prefixo(arv)
    tp = estimar_tokens(prefixo)
    _, ts_medio = _amostra_sufixo()
    n_fb = _n_arvore_inteira()

    print("=== Cache de contexto: plano (proxy chars/3, sem API) ===")
    print(f"  temas na arvore: {len(_todos(arv))}")
    print(f"  prefixo estatico (instrucoes + arvore): ~{tp:,} tokens")
    print(f"  sufixo por questao (origem + enunciado): ~{ts_medio:,} tokens")
    print(f"  questoes que ja recebem a arvore inteira (fallback): {n_fb}")
    print()

    casos = []
    if n:
        casos.append((f"projecao N={n}", n))
    if n_fb:
        casos.append((f"fallback aplicado ({n_fb})", n_fb))
    casos.append(("verificador (261 publicadas)", 261))
    casos.append(("projecao N=1000", 1000))

    print(f"  {'caso':32s} {'sem cache':>12s} {'com cache':>12s} {'economia':>10s}")
    for nome, k in casos:
        sem = k * (tp + ts_medio)
        com = tp + k * (tp * desconto + ts_medio)  # escrita 1x + leitura descontada
        eco = 1 - com / sem if sem else 0
        print(f"  {nome:32s} {sem/1e6:10.2f}M {com/1e6:10.2f}M {eco:9.0%}")

    if preco_in_por_milhao:
        k = n or 1000
        sem = k * (tp + ts_medio) / 1e6 * preco_in_por_milhao
        com = (tp + k * (tp * desconto + ts_medio)) / 1e6 * preco_in_por_milhao
        # armazenamento: aprox. 1h (preco de storage ~ entrada/hora; verificar no contrato)
        print(f"\n  a US$ {preco_in_por_milhao}/M entrada, para N={k}: "
              f"sem cache US$ {sem:.2f} -> com cache US$ {com:.2f} (economia US$ {sem-com:.2f})")
        print(f"  (armazenamento do cache por ~{ttl_horas:.0f}h NAO incluido; verificar preco.)")
    print("\n  Observacao: o token em cache costuma ser cobrado a ~25% do token de entrada;")
    print("  ajuste --desconto conforme a tabela vigente. Este plano NAO faz chamada de API.")


class GeradorCache:
    """Gera respostas usando um cache de contexto do Gemini para o prefixo (a arvore).

    O prompt do juiz/verificador tem a forma:

        <INSTRUCOES>
        ---
        DISCIPLINA DE ORIGEM: ...
        ASSUNTO DE ORIGEM: ...
        QUESTAO:
        <texto>
        CANDIDATOS (id | caminho):
        <ARVORE>

    No verificador, o bloco de CANDIDATOS e CONSTANTE (a arvore inteira). Reordenamos para
    [INSTRUCOES + ARVORE] (prefixo cacheado) + [--- + DISCIPLINA/ASSUNTO/QUESTAO] (variavel).
    Assim o prefixo de ~9 mil tokens e enviado UMA vez; as demais chamadas pagam so o sufixo.

    Ligado por `CONTEXT_CACHE=1` em src.verificar_arvore. A chave do cache EM DISCO segue
    sendo o prompt ORIGINAL (via judge.uma_chamada), entao nada e repago por habilita-lo.
    """

    def __init__(self, arv, model, ttl="1800s", manter=False):
        import os

        from google import genai
        from google.genai import types

        self.model = model
        self.ttl = ttl
        self.manter = manter
        self.types = types
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._prefixo = None
        self._cache = None
        self.stats = {"criado": 0, "chamadas": 0, "tokens_in": 0, "tokens_cacheados": 0, "tokens_out": 0}

    @staticmethod
    def _partes(prompt):
        instr, resto = prompt.split("\n---\n", 1)
        cab, arvore = resto.split("\n\nCANDIDATOS (id | caminho):\n", 1)
        return instr.rstrip(), cab, arvore

    def _prefixo_de(self, prompt):
        instr, _, arvore = self._partes(prompt)
        return instr + "\n\nCANDIDATOS (id | caminho):\n" + arvore

    def _sufixo_de(self, prompt):
        _, cab, _ = self._partes(prompt)
        return "\n---\n" + cab

    def __call__(self, model, prompt, temperature):
        if model != self.model:
            raise ValueError(f"GeradorCache esta ligado a {self.model}, mas recebeu {model}")
        prefixo = self._prefixo_de(prompt)
        if self._cache is None:
            self._prefixo = prefixo
            self._cache = self.client.caches.create(
                model=model,
                config=self.types.CreateCachedContentConfig(
                    display_name="arvore_temas",
                    contents=[self.types.Content(role="user", parts=[self.types.Part(text=prefixo)])],
                    ttl=self.ttl,
                ),
            )
            self.stats["criado"] += 1
        elif prefixo != self._prefixo:
            raise ValueError("o bloco de candidatos mudou entre chamadas; o cache exige prefixo constante")
        r = self.client.models.generate_content(
            model=model,
            contents=self._sufixo_de(prompt),
            config=self.types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                cached_content=self._cache.name,
            ),
        )
        self.stats["chamadas"] += 1
        um = getattr(r, "usage_metadata", None)
        if um:
            self.stats["tokens_in"] += getattr(um, "prompt_token_count", 0) or 0
            self.stats["tokens_cacheados"] += getattr(um, "cached_content_token_count", 0) or 0
            self.stats["tokens_out"] += getattr(um, "candidates_token_count", 0) or 0
        return r.text

    def nome(self):
        return self._cache.name if self._cache is not None else None

    def fechar(self):
        if self._cache is not None and not self.manter:
            try:
                self.client.caches.delete(name=self._cache.name)
            except Exception:
                pass
            self._cache = None


def validar(arv, n=2):
    """Faz n votos do verificador COM cache e compara com os votos guardados (USA API, centavos)."""
    import pandas as pd

    from src import judge as J

    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("").set_index("id", drop=False)
    pub = pd.read_csv(OUT / "publicacao_congelada.csv", dtype=str).fillna("")
    ids = pub.loc[pub["decisao"] == "publicar", "id"].tolist()[:n]
    guardado = {}
    vp = OUT / "votos_verificacao.jsonl"
    if vp.exists():
        for linha in vp.open(encoding="utf-8"):
            x = json.loads(linha)
            guardado[x["id"]] = x["vote"]
    todos = _todos(arv)
    g = GeradorCache(arv, "gemini-3.1-flash-lite", ttl="600s")
    print("cache de contexto: (criado na 1a chamada)")
    for i in ids:
        prompt = J.montar_prompt(arv, q.loc[i], todos)
        txt = g("gemini-3.1-flash-lite", prompt, 0.0)
        antes = guardado.get(i)
        print(f"\n{i}: guardado tema={antes.get('tema_id') if antes else None} fora={antes.get('fora') if antes else None}")
        print(f"     com cache -> {(txt or '')[:200]}")
    print(f"\nstats: {g.stats}")
    g.fechar()


def criar_e_testar(arv, model="gemini-3.1-flash-lite", ttl="1800s"):
    """Cria o cache de verdade e faz 1 chamada de teste. USA API (poucos centavos)."""
    import os

    import pandas as pd
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prefixo = montar_prefixo(arv)
    print(f"criando cache ({len(prefixo)//3} tokens ~)...")
    cache = client.caches.create(
        model=model,
        config=types.CreateCachedContentConfig(
            display_name="arvore_temas",
            contents=[prefixo],
            ttl=ttl,
        ),
    )
    print(f"cache criado: {cache.name}  (ttl={ttl})")

    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")
    row = q.iloc[0]
    r = client.models.generate_content(
        model=model,
        contents=montar_sufixo(row),
        config=types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json", cached_content=cache.name
        ),
    )
    um = getattr(r, "usage_metadata", None)
    print("resposta:", (r.text or "")[:180])
    if um:
        print(f"tokens_in={getattr(um,'prompt_token_count',0)} "
              f"cacheados={getattr(um,'cached_content_token_count',0)}")
    client.caches.delete(name=cache.name)
    print("cache apagado.")


def main():
    ap = argparse.ArgumentParser(description="Cache de contexto para o prefixo repetido (arvore).")
    ap.add_argument("--dry-run", action="store_true", help="so o plano em tokens (default; gratis)")
    ap.add_argument("--criar", action="store_true", help="cria o cache de verdade (USA API)")
    ap.add_argument("--validar", action="store_true", help="n votos com cache vs guardados (USA API)")
    ap.add_argument("--n-validar", type=int, default=2, help="quantos votos validar")
    ap.add_argument("--n", type=int, default=None, help="projeta para N questoes")
    ap.add_argument("--desconto", type=float, default=0.25, help="fracao do preco paga por token em cache")
    ap.add_argument("--preco-in", type=float, default=None, help="US$ por milhao de tokens de entrada")
    ap.add_argument("--modelo", default="gemini-3.1-flash-lite")
    args = ap.parse_args()

    arv = Arvore()
    if args.validar:
        validar(arv, n=args.n_validar)
    elif args.criar:
        criar_e_testar(arv, model=args.modelo)
    else:
        planejar(arv, n=args.n, desconto=args.desconto, preco_in_por_milhao=args.preco_in)


if __name__ == "__main__":
    main()
