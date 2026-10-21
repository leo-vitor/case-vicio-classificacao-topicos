"""Validador do enriquecimento juridico (offline, sem LLM).

Duas responsabilidades:

1. `parse_saida`: extrai objetos JSON de uma saida bruta de modelo, ignorando
   cercas markdown, blocos de codigo, prosa e resultados de execucao.
2. `validar`: aplica o contrato do briefing (schema, hierarquia, limites por
   campo, whitelist de leis, blacklist de adjetivos, colisoes de vocabulario).

O modulo nao escreve arquivo, nao acessa rede e nao guarda estado: quem grava e
o CLI em `scripts/ingerir.py`.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SCHEMA = [
    "id_tema",
    "titulo",
    "sinonimos",
    "institutos",
    "leis",
    "distincoes",
    "texto_enriquecido",
]

# Limites do briefing (prompt v2). O piso de sinonimos caiu de 3 para 2:
# nenhuma metrica depende dele e forcar um terceiro termo gera preenchimento.
# Volta a 3 se a ablacao por campo mostrar ganho.
N_SIN = (2, 5)
N_INST = (0, 5)
SIN_MAX = 40
INST_MAX = 35
DIF_MIN, DIF_MAX = 60, 160
TEXTO_MIN, TEXTO_MAX = 120, 250
LINHA_MAX = 700  # apenas aviso: o teto conflita com titulos longos + 2 distincoes

BLACKLIST = (
    "fático", "fática", "fático", "limpo", "cru", "cego", "puro", "brutal",
    "sangrento", "letal", "amargo", "triste", "rústico", "imundo", "podre",
    "escuro", "mudo", "inerte", "covarde", "sádico", "desolador",
)

# 20 nos de nivel 1 duplicados, sem filhos e sem descricao: nao enriquecem,
# viram filtro de disciplina no passo 5.
EXCLUIDOS = frozenset({
    "6716", "6717", "6718", "6719", "6720", "6721", "6722", "6723", "6724",
    "6725", "6726", "6727", "6728",
    "6732", "6733", "6734", "6735", "6736", "6737", "6738",
})

# Ordem de geracao. Criminologia e Legislagem Especial ficam no fim de proposito:
# sao as disciplinas menores e as que mais sofrem colisao de vocabulario.
ORDEM_DISCIPLINA = [
    "Penal",
    "Processo Penal",
    "Criminologia",
    "Direito Penal - Legislação Especial",
]


@dataclass
class Taxonomia:
    titulo: dict[str, str]
    parent: dict[str, str]
    nivel: dict[str, int]
    status: dict[str, str]
    disciplina: dict[str, str]
    filhos: dict[str, list[str]]
    leis: set[str]
    sinonimos: set[str]

    @classmethod
    def carregar(cls, temas=None, dicionario=None) -> "Taxonomia":
        temas = Path(temas or DATA / "temas.csv")
        dicionario = Path(dicionario or DATA / "dicionario_juridico.csv")

        with temas.open(encoding="utf-8") as fh:
            linhas = list(csv.DictReader(fh))
        titulo = {r["tema_id"]: r["titulo"] for r in linhas}
        parent = {r["tema_id"]: r["parent_id"] for r in linhas if r["parent_id"]}
        nivel = {r["tema_id"]: int(r["nivel"]) for r in linhas}
        status = {r["tema_id"]: r["status"] for r in linhas}
        disciplina = {r["tema_id"]: r["disciplina"] for r in linhas}

        filhos: dict[str, list[str]] = {}
        for tid, pid in parent.items():
            filhos.setdefault(pid, []).append(tid)

        with dicionario.open(encoding="utf-8") as fh:
            dic = list(csv.DictReader(fh))
        leis = {r["chave"] for r in dic if r["tipo"].strip().lower() in {"lei", "leis"}}
        sinonimos = {r["chave"] for r in dic if r["tipo"].strip().lower() == "sinonimo"}

        return cls(titulo, parent, nivel, status, disciplina, filhos, leis, sinonimos)

    def elegivel(self, tid: str) -> bool:
        return (
            tid in self.titulo
            and self.status.get(tid) == "active"
            and self.nivel.get(tid, 0) >= 1
            and tid not in EXCLUIDOS
        )

    def universo(self) -> list[str]:
        """Os 351 nos enriqueciveis, na ordem de geracao (disciplina, id)."""
        ordem = {d: i for i, d in enumerate(ORDEM_DISCIPLINA)}
        ids = [t for t in self.titulo if self.elegivel(t)]
        return sorted(ids, key=lambda t: (ordem.get(self.disciplina[t], 99), int(t)))

    def familia(self, tid: str) -> str:
        """No de nivel 1 que ancora o tema (o proprio, se ja for nivel 1)."""
        return tid if self.nivel.get(tid) == 1 else self.parent.get(tid, tid)

    def irmaos(self, tid: str) -> list[str]:
        p = self.parent.get(tid)
        return [c for c in self.filhos.get(p, []) if c != tid and self.elegivel(c)] if p else []


# --------------------------------------------------------------------------
# Parsing tolerante
# --------------------------------------------------------------------------

def _sem_cercas(texto: str) -> str:
    return "\n".join(
        l for l in texto.splitlines() if not re.match(r"^\s*```", l)
    )


def _objetos_balanceados(texto: str) -> list[str]:
    """Recorta objetos {...} de nivel zero, respeitando strings e escapes."""
    blocos, profundidade, inicio, em_string, escape = [], 0, None, False, False
    for i, ch in enumerate(texto):
        if em_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                em_string = False
            continue
        if ch == '"':
            em_string = True
        elif ch == "{":
            if profundidade == 0:
                inicio = i
            profundidade += 1
        elif ch == "}":
            if profundidade:
                profundidade -= 1
                if profundidade == 0 and inicio is not None:
                    blocos.append(texto[inicio : i + 1])
                    inicio = None
    return blocos


def parse_saida(texto: str) -> tuple[list[dict], list[str]]:
    """Extrai objetos de uma resposta bruta. Devolve (objetos, avisos)."""
    avisos: list[str] = []
    limpo = _sem_cercas(texto)

    # 1) resposta inteira e um JSON valido
    for tentativa in (limpo, texto):
        try:
            bruto = json.loads(tentativa.strip())
        except Exception:
            continue
        if isinstance(bruto, dict):
            for chave in ("temas", "objetos", "data", "items"):
                if isinstance(bruto.get(chave), list):
                    bruto = bruto[chave]
                    break
            else:
                bruto = [bruto]
        if isinstance(bruto, list):
            objs = [o for o in bruto if isinstance(o, dict) and "id_tema" in o]
            if objs:
                return objs, avisos

    # 2) varredura de objetos balanceados
    objs, descartados = [], 0
    for bloco in _objetos_balanceados(limpo):
        try:
            o = json.loads(bloco)
        except Exception:
            descartados += 1
            continue
        if isinstance(o, dict) and "id_tema" in o:
            objs.append(o)
        else:
            descartados += 1
    if descartados:
        avisos.append(f"{descartados} bloco(s) JSON sem id_tema descartado(s)")

    # 3) dedupe: mantem a ultima ocorrencia de cada id
    vistos: dict[str, dict] = {}
    repetidos = []
    for o in objs:
        tid = str(o.get("id_tema", ""))
        if tid in vistos:
            repetidos.append(tid)
        vistos[tid] = o
    if repetidos:
        avisos.append(f"ids repetidos na saida (mantida a ultima): {', '.join(sorted(set(repetidos)))}")
    return list(vistos.values()), avisos


# --------------------------------------------------------------------------
# Validacao
# --------------------------------------------------------------------------

@dataclass
class Item:
    id: str
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.erros


def _termos(o: dict) -> set[str]:
    termos = set()
    for chave in ("sinonimos", "institutos"):
        for t in o.get(chave) or []:
            if isinstance(t, str):
                termos.add(t.strip().lower())
    return {t for t in termos if t}


def _colisoes(o: dict, outros: list[dict], tax: Taxonomia) -> tuple[list[str], list[str]]:
    """Termo repetido com pai/filho (erro) ou irmao (aviso)."""
    tid = str(o["id_tema"])
    meus = _termos(o)
    erros, avisos = [], []
    for outro in outros:
        oid = str(outro["id_tema"])
        if oid == tid or not meus:
            continue
        comum = meus & _termos(outro)
        if not comum:
            continue
        rel = None
        if tax.parent.get(tid) == oid:
            rel = "pai"
        elif tax.parent.get(oid) == tid:
            rel = "filho"
        elif tax.parent.get(tid) == tax.parent.get(oid):
            rel = "irmao"
        if rel is None:
            continue
        alvo = f"{rel} {oid}: {', '.join(sorted(comum))}"
        (erros if rel in {"pai", "filho"} else avisos).append(f"colisao com {alvo}")
    return erros, avisos


def validar(
    lote: list[dict],
    tax: Taxonomia,
    existentes: list[dict] | None = None,
) -> list[Item]:
    """Valida um lote contra o contrato. Nao altera os objetos."""
    existentes = existentes or []
    por_id = {str(o.get("id_tema")): o for o in existentes}
    todos = existentes + lote
    saida: list[Item] = []

    for o in lote:
        tid = str(o.get("id_tema", ""))
        it = Item(id=tid)
        saida.append(it)

        # --- schema ---
        if list(o.keys()) != SCHEMA:
            faltando = [k for k in SCHEMA if k not in o]
            extras = [k for k in o if k not in SCHEMA]
            det = []
            if faltando:
                det.append(f"falta {faltando}")
            if extras:
                det.append(f"sobra {extras}")
            if not det:
                det.append("ordem das chaves diferente")
            it.erros.append("schema: " + "; ".join(det))
            continue

        if not isinstance(o["id_tema"], str):
            it.erros.append("id_tema deve ser string")

        # --- existencia e titulo ---
        if tid not in tax.titulo:
            it.erros.append("id inexistente na taxonomia")
            continue
        if not tax.elegivel(tid):
            it.erros.append(
                f"nao elegivel (status={tax.status.get(tid)}, nivel={tax.nivel.get(tid)})"
            )
        if o["titulo"] != tax.titulo[tid]:
            it.erros.append(f"titulo divergente do CSV: {o['titulo']!r}")
        if tid in por_id:
            it.erros.append("id ja existe no arquivo")

        # --- sinonimos ---
        sin = o["sinonimos"]
        if not isinstance(sin, list) or not all(isinstance(x, str) for x in sin):
            it.erros.append("sinonimos deve ser lista de strings")
        else:
            if not (N_SIN[0] <= len(sin) <= N_SIN[1]):
                it.erros.append(f"sinonimos: {len(sin)} itens (esperado {N_SIN[0]}-{N_SIN[1]})")
            for x in sin:
                if len(x) > SIN_MAX:
                    it.erros.append(f"sinonimo longo ({len(x)}): {x!r}")
                if not x.strip():
                    it.erros.append("sinonimo vazio")
            if len({x.lower() for x in sin}) != len(sin):
                it.erros.append("sinonimos repetidos")

        # --- institutos ---
        inst = o["institutos"]
        if not isinstance(inst, list) or not all(isinstance(x, str) for x in inst):
            it.erros.append("institutos deve ser lista de strings")
        else:
            if not (N_INST[0] <= len(inst) <= N_INST[1]):
                it.erros.append(f"institutos: {len(inst)} itens (max {N_INST[1]})")
            for x in inst:
                if len(x) > INST_MAX:
                    it.erros.append(f"instituto longo ({len(x)}): {x!r}")

        # --- leis ---
        if not isinstance(o["leis"], list) or not all(isinstance(x, str) for x in o["leis"]):
            it.erros.append("leis deve ser lista de strings")
        else:
            fora = [x for x in o["leis"] if x not in tax.leis]
            if fora:
                it.erros.append(f"lei fora da whitelist: {fora}")
            if len(set(o["leis"])) != len(o["leis"]):
                it.erros.append("leis repetidas")

        # --- distincoes ---
        if not isinstance(o["distincoes"], list):
            it.erros.append("distincoes deve ser lista")
        else:
            vistos = set()
            for d in o["distincoes"]:
                if not isinstance(d, dict) or set(d.keys()) != {"id_tema", "diferenca"}:
                    it.erros.append(f"distincao com chaves inesperadas: {d}")
                    continue
                alvo = str(d["id_tema"])
                if alvo == tid:
                    it.erros.append("distincao aponta para o proprio tema")
                    continue
                if alvo in vistos:
                    it.erros.append(f"distincao repetida para {alvo}")
                    continue
                vistos.add(alvo)
                if alvo not in tax.titulo:
                    it.erros.append(f"distincao para id inexistente: {alvo}")
                    continue
                if tax.parent.get(tid) != tax.parent.get(alvo):
                    it.erros.append(f"distincao nao-irma: {tid} -> {alvo}")
                if not tax.elegivel(alvo):
                    it.erros.append(f"distincao para no nao enriquecivel: {alvo}")
                n = len(d["diferenca"])
                if not (DIF_MIN <= n <= DIF_MAX):
                    it.erros.append(f"diferenca {alvo}: {n} chars (esperado {DIF_MIN}-{DIF_MAX})")

        # --- texto ---
        txt = o["texto_enriquecido"]
        if not isinstance(txt, str):
            it.erros.append("texto_enriquecido deve ser string")
        else:
            n = len(txt)
            if not (TEXTO_MIN <= n <= TEXTO_MAX):
                it.erros.append(f"texto: {n} chars (esperado {TEXTO_MIN}-{TEXTO_MAX})")
            if txt.strip() != txt:
                it.avisos.append("texto com espaco nas pontas")
            if "\n" in txt:
                it.erros.append("texto com quebra de linha")

        # --- blacklist ---
        corpo = " ".join(
            [txt if isinstance(txt, str) else ""]
            + [x for x in (sin if isinstance(sin, list) else []) if isinstance(x, str)]
            + [x for x in (inst if isinstance(inst, list) else []) if isinstance(x, str)]
        ).lower()
        achados = [w for w in BLACKLIST if w in corpo]
        if achados:
            it.erros.append(f"adjetivo da blacklist: {achados}")

        # --- colisoes ---
        erros_col, avisos_col = _colisoes(o, todos, tax)
        it.erros.extend(erros_col)
        it.avisos.extend(avisos_col)

        # --- tamanho da linha ---
        linha = json.dumps(o, ensure_ascii=False)
        if len(linha) > LINHA_MAX:
            it.avisos.append(f"linha com {len(linha)} chars (aviso, nao bloqueia)")

    return saida


# --------------------------------------------------------------------------
# Leitura do arquivo e plano de rodadas
# --------------------------------------------------------------------------

def ler_arquivo(caminho: Path) -> tuple[list[dict], list[str]]:
    """Le o JSONL. Devolve (objetos, linhas invalidas)."""
    objs, invalidas = [], []
    if not Path(caminho).exists():
        return objs, invalidas
    for n, linha in enumerate(Path(caminho).read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        try:
            o = json.loads(linha)
        except Exception:
            invalidas.append(f"linha {n}: JSON invalido")
            continue
        if not isinstance(o, dict) or "id_tema" not in o:
            invalidas.append(f"linha {n}: nao e objeto de tema")
            continue
        objs.append(o)
    return objs, invalidas


def buracos(ids: list[str], tax: Taxonomia) -> list[str]:
    """Elegiveis que ficaram para tras na ordem de geracao."""
    universo = tax.universo()
    if not ids:
        return universo
    pos = {t: i for i, t in enumerate(universo)}
    ultimo = max((pos.get(t, -1) for t in ids), default=-1)
    faltando = [t for t in universo[: ultimo + 1] if t not in set(ids)]
    return faltando


def proxima_rodada(
    ids: list[str],
    tax: Taxonomia,
    n: int = 20,
    apos: str | None = None,
) -> list[str]:
    """Proximos N nos, cortando no fim de familia (18-22 na pratica)."""
    universo = tax.universo()
    if apos:
        if apos not in universo:
            raise ValueError(f"{apos} nao esta no universo enriquecivel")
        inicio = universo.index(apos)
    elif ids:
        pos = {t: i for i, t in enumerate(universo)}
        inicio = max((pos.get(t, -1) for t in ids), default=-1) + 1
    else:
        inicio = 0

    # agrupa por familia mantendo a ordem
    grupos: list[list[str]] = []
    for tid in universo[inicio:]:
        fam = tax.familia(tid)
        if grupos and tax.familia(grupos[-1][0]) == fam:
            grupos[-1].append(tid)
        else:
            grupos.append([tid])

    escolhidos: list[str] = []
    for grupo in grupos:
        if len(escolhidos) >= n:
            break
        if len(escolhidos) >= 18 and len(escolhidos) + len(grupo) > 22:
            break
        escolhidos.extend(grupo)
    return escolhidos
