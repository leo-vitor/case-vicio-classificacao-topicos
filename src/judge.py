"""Etapa 3: o LLM escolhe o tema entre os candidatos. Varias rodadas por questao.

Tudo fica em cache em disco (outputs/cache/judge). Rodar de novo nao gasta chamadas.
"""
import hashlib
import threading
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.config import (
    CACHE, JUDGE_BACKEND, JUDGE_MODELS, JUDGE_WORKERS, LIMIT, OUT, ROOT, RUNS_PER_MODEL, TEMPERATURE,
)
from src.temas import Arvore

PROMPT = (ROOT / "prompts" / "judge_prompt.md").read_text(encoding="utf-8")
JCACHE = CACHE / "judge"
JCACHE.mkdir(exist_ok=True)
STATS = {"chamadas": 0, "cache": 0, "tokens_in": 0, "tokens_out": 0, "tokens_pensando": 0, "erros": 0}
RPM = int(os.getenv("RPM", "0"))
_LOCK = threading.Lock()
_ULTIMA = [0.0]


def _esperar_vez():
    if RPM <= 0:
        return
    with _LOCK:
        espera = _ULTIMA[0] + 60.0 / RPM - time.time()
        if espera > 0:
            time.sleep(espera)
        _ULTIMA[0] = time.time()


def montar_prompt(arv, row, cand_ids):
    cands = "\n".join(f"{t} | {arv.caminho[t]}" for t in cand_ids)
    p = PROMPT
    for k, v in {
        "{disciplina_origem}": row["disciplina_origem"] or "(vazio)",
        "{assunto_origem}": row["assunto_origem"] or "(vazio)",
        "{texto}": row["texto"][:3500],
        "{candidatos}": cands,
    }.items():
        p = p.replace(k, v)
    return p


def _gemini(model, prompt, temperature):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    ultimo = None
    for tent in range(8):
        try:
            _esperar_vez()
            r = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature, response_mime_type="application/json"
                ),
            )
            um = getattr(r, "usage_metadata", None)
            if um:
                STATS["tokens_in"] += getattr(um, "prompt_token_count", 0) or 0
                STATS["tokens_out"] += getattr(um, "candidates_token_count", 0) or 0
                STATS["tokens_pensando"] += getattr(um, "thoughts_token_count", 0) or 0
            txt = r.text
            if txt is None:
                info = ""
                try:
                    fb = getattr(r, "prompt_feedback", None)
                    cand = (r.candidates or [None])[0]
                    info = f"block={getattr(fb, 'block_reason', None)} finish={getattr(cand, 'finish_reason', None)}"
                except Exception:
                    pass
                return "BLOQUEADA " + info
            return txt
        except Exception as e:
            ultimo = e
            if "spending cap" in str(e).lower():
                raise RuntimeError(f"Teto de gasto do projeto atingido: {e}")            
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(25 + 10 * tent)
            else:
                time.sleep(2 ** tent)
    raise RuntimeError(f"Falha apos 8 tentativas: {ultimo}")


def _mock(qid, cand_ids, run):
    """Backend de teste: nao e IA. So serve para verificar o fluxo do pipeline."""
    h = int(hashlib.md5(qid.encode()).hexdigest(), 16)
    idx = 1 if (h % 5 == 0 and run == 1 and len(cand_ids) > 1) else 0
    return json.dumps(
        {"fora": False, "tema_central_id": cand_ids[idx], "extras_ids": [], "confianca": 0.9, "motivo": "mock"}
    )


def _parse_bruto(txt, cand_ids):
    try:
        m = re.search(r"\{.*\}", txt, flags=re.S)
        d = json.loads(m.group(0))
    except Exception:
        return None
    if d.get("fora"):
        return {"fora": True, "tema_id": None, "extras": [], "conf": float(d.get("confianca") or 0), "motivo": str(d.get("motivo", ""))}
    tid = str(d.get("tema_central_id")) if d.get("tema_central_id") is not None else None
    if tid not in cand_ids:
        return None
    ex = [str(x) for x in (d.get("extras_ids") or []) if str(x) in cand_ids and str(x) != tid][:3]
    conf = max(0.0, min(1.0, float(d.get("confianca") or 0)))
    return {"fora": False, "tema_id": tid, "extras": ex, "conf": conf, "motivo": str(d.get("motivo", ""))}

def _parse(txt, cand_ids):
    try:
        return _parse_bruto(txt, cand_ids)
    except (ValueError, TypeError, AttributeError):
        return None


def uma_chamada(arv, row, cand_ids, model, run, gerar=None):
    """Um voto. `gerar(model, prompt, temp)` opcional substitui a chamada crua.

    Serve para injetar o cache de contexto (src.contexto_cache.GeradorCache): a chave do
    cache EM DISCO continua sendo o prompt ORIGINAL, entao nada e repago por isso.
    """
    prompt = montar_prompt(arv, row, cand_ids)
    temp = 0.0 if RUNS_PER_MODEL == 1 else TEMPERATURE
    key = hashlib.sha256(f"{JUDGE_BACKEND}|{model}|{temp}|{run}|{prompt}".encode()).hexdigest()
    f = JCACHE / f"{key}.json"
    if f.exists():
        STATS["cache"] += 1
        txt = json.loads(f.read_text(encoding="utf-8"))["txt"]
    else:
        STATS["chamadas"] += 1
        if gerar is not None:
            txt = gerar(model, prompt, temp)
        elif JUDGE_BACKEND == "mock":
            txt = _mock(row["id"], cand_ids, run)
        else:
            txt = _gemini(model, prompt, temp)
        f.write_text(json.dumps({"txt": txt}, ensure_ascii=False), encoding="utf-8")
    v = _parse(txt, set(cand_ids))
    if v is None:
        STATS["erros"] += 1
        if (txt or "").startswith("BLOQUEADA"):
            motivo = "resposta bloqueada pelo modelo (revisar manualmente)"
        else:
            f.unlink(missing_ok=True)
            motivo = "saida invalida"
        v = {"fora": False, "tema_id": None, "extras": [], "conf": 0.0, "motivo": motivo}
    v.update({"model": model, "run": run})
    return v


def main():
    arv = Arvore()
    q = pd.read_csv(OUT / "questoes_limpas.csv", dtype=str).fillna("")
    if LIMIT:
        q = q.head(LIMIT)
    cands = json.loads((OUT / "candidatos.json").read_text(encoding="utf-8"))
    t0 = time.time()

    def tarefa(i):
        row = q.iloc[i]
        cid = cands[row["id"]]["candidatos"]
        votos = [
            uma_chamada(arv, row, cid, m, r) for m in JUDGE_MODELS for r in range(RUNS_PER_MODEL)
        ]
        return {"id": row["id"], "votes": votos}

    with ThreadPoolExecutor(max_workers=JUDGE_WORKERS) as ex:
        res = list(ex.map(tarefa, range(len(q))))
    with open(OUT / "votos.jsonl", "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    STATS["segundos"] = round(time.time() - t0, 1)
    STATS["modelos"] = JUDGE_MODELS
    STATS["rodadas_por_modelo"] = RUNS_PER_MODEL
    (OUT / "uso.json").write_text(json.dumps(STATS, indent=2), encoding="utf-8")
    from src import uso  # log append-only, sobrevive a execucoes futuras
    uso.registrar("judge", STATS, extra={"questoes": len(res)})
    print("Resumo:", STATS)


if __name__ == "__main__":
    main()
