#!/usr/bin/env python3
"""Ingere a saida bruta do modelo no arquivo de enriquecimento.

Uso tipico (macOS, resposta copiada do navegador):

    pbpaste | .venv/bin/python scripts/ingerir.py            # dry-run
    pbpaste | .venv/bin/python scripts/ingerir.py --commit   # valida e anexa
    .venv/bin/python scripts/ingerir.py --auditar            # estado do arquivo
    .venv/bin/python scripts/ingerir.py --proxima 20         # proxima rodada

O parser aceita saida suja: cerca markdown, bloco de codigo, prosa e resultado
de execucao. Só entra objeto JSON com `id_tema` e `titulo`.

Codigos de saida: 0 ok, 1 ha objeto reprovado, 2 recusa (entrada ou buraco).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.validador_enriquecimento import (  # noqa: E402
    Item,
    Taxonomia,
    buracos,
    ler_arquivo,
    parse_saida,
    proxima_rodada,
    validar,
)

PADRAO = ROOT / "enriquecimento_v01.jsonl"


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def _tabela(itens: list[Item]) -> None:
    if not itens:
        return
    largura = max(len(i.id) for i in itens)
    for it in itens:
        marca = "ok  " if it.ok else "ERRO"
        print(f"  {marca} {it.id:<{largura}}")
        for e in it.erros:
            print(f"         - {e}")
        for a in it.avisos:
            print(f"         ~ {a}")


def _resumo(itens: list[Item]) -> tuple[int, int]:
    ok = sum(1 for i in itens if i.ok)
    return ok, len(itens) - ok


def _bloco_rodada(ids: list[str], tax: Taxonomia) -> None:
    if not ids:
        print("Nada a gerar: o universo enriquecivel acabou.")
        return
    print(f"\nRodada com {len(ids)} objetos ({ids[0]} a {ids[-1]}):\n")
    print(f"{'id':<6} {'pai':<6} {'nv':<3} titulo")
    for tid in ids:
        print(f"{tid:<6} {tax.parent.get(tid, '-'):<6} {tax.nivel.get(tid, 0):<3} {tax.titulo[tid]}")
    familias = []
    for tid in ids:
        fam = tax.familia(tid)
        if not familias or familias[-1] != fam:
            familias.append(fam)
    print(f"\nFamilias: {len(familias)} -> {', '.join(familias)}")
    print(f"Total esperado: {len(ids)} objetos.")
    print("Corte no fim de familia. Nao execute codigo: devolva apenas as linhas JSONL.")


def cmd_ingerir(args, tax: Taxonomia) -> int:
    if args.de:
        texto = Path(args.de).read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            print(
                "Nada na entrada. Use `pbpaste | ...` ou `--de resposta.txt`.\n"
                "Para ver o estado do arquivo: --auditar",
                file=sys.stderr,
            )
            return 2
        texto = sys.stdin.read()

    if not texto.strip():
        print("Entrada vazia.", file=sys.stderr)
        return 2

    lote, avisos = parse_saida(texto)
    print(f"Objetos reconhecidos: {len(lote)}")
    for a in avisos:
        print(f"  ~ {a}")
    if not lote:
        print("Nenhum objeto JSON com id_tema encontrado na entrada.", file=sys.stderr)
        return 2

    existentes, invalidas = ler_arquivo(Path(args.arquivo))
    if invalidas:
        print("\nArquivo de destino com linhas invalidas:")
        for i in invalidas:
            print(f"  ! {i}")
        return 2

    itens = validar(lote, tax, existentes)
    ok, reprovados = _resumo(itens)
    print(f"\nValidacao: {ok} ok, {reprovados} reprovado(s)")
    _tabela(itens)
    if reprovados:
        print("\nNada foi gravado. Corrija os objetos acima e reenvie.")
        return 1

    universo = tax.universo()
    pos = {t: i for i, t in enumerate(universo)}
    ids_lote = sorted((i.id for i in itens), key=pos.get)
    por_id_lote = {str(o["id_tema"]): o for o in lote}

    # O lote tem de ser um trecho contiguo do universo. Vale tanto para anexar
    # no fim quanto para preencher buraco no meio: o que nao pode e pular id.
    inicio = pos[ids_lote[0]]
    esperado = universo[inicio : inicio + len(ids_lote)]
    presentes = {o["id_tema"] for o in existentes}
    if ids_lote != esperado:
        faltando = [t for t in esperado if t not in presentes | set(ids_lote)]
        print("\nBLOQUEADO: o lote nao e um trecho contiguo do universo.")
        print(f"  recebido: {', '.join(ids_lote)}")
        print(f"  esperado: {', '.join(esperado)}")
        if faltando:
            print(f"  faltam: {', '.join(faltando)}")
        print("  Use --permitir-buraco apenas se souber exatamente o que esta fazendo.")
        if not args.permitir_buraco:
            return 2
        print("  --permitir-buraco ativo: gravando mesmo assim.")

    # merged na ordem canonica, preservando os objetos ja existentes
    juntos = {o["id_tema"]: o for o in existentes}
    for tid in ids_lote:
        if tid in juntos:
            print(f"\nBLOQUEADO: {tid} ja existe no arquivo.")
            return 2
        juntos[tid] = por_id_lote[tid]
    ordenados = sorted(juntos, key=pos.get)

    ordem_antiga = [o["id_tema"] for o in existentes]
    if [t for t in ordenados if t in presentes] != ordem_antiga:
        print("\nAviso: o arquivo sera reordenado para a ordem canonica (disciplina, id).")

    total = len(ordenados)
    restantes = len(universo) - total
    faltam_depois = [t for t in universo if t not in juntos]

    if args.commit:
        linhas = [json.dumps(juntos[t], ensure_ascii=False) for t in ordenados]
        destino = Path(args.arquivo)
        tmp = destino.with_suffix(destino.suffix + ".tmp")
        tmp.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        tmp.replace(destino)
        print(f"\nGravado: {len(ids_lote)} objeto(s) em {destino}")
        print(f"  total: {total} | restantes: {restantes} | sha256: {_sha(destino)}")
        if faltam_depois:
            print(f"  faltam {len(faltam_depois)}: {', '.join(faltam_depois[:12])}" + (" ..." if len(faltam_depois) > 12 else ""))
            print(f"  proximo id: {faltam_depois[0]}")
        else:
            print("  universo enriquecivel completo.")
    else:
        print(f"\nDry-run: nada foi gravado. Seriam {len(ids_lote)} objeto(s).")
        print(f"  total passaria a {total} | restantes: {restantes}")
        if faltam_depois:
            print(f"  faltam {len(faltam_depois)}: {', '.join(faltam_depois[:12])}" + (" ..." if len(faltam_depois) > 12 else ""))
    return 0


def cmd_auditar(args, tax: Taxonomia) -> int:
    caminho = Path(args.arquivo)
    objs, invalidas = ler_arquivo(caminho)
    universo = tax.universo()
    ids = [o["id_tema"] for o in objs]
    conjunto = set(ids)

    print(f"Arquivo: {caminho}")
    if caminho.exists():
        print(f"  bytes: {caminho.stat().st_size} | linhas: {len(objs) + len(invalidas)} | sha256: {_sha(caminho)}")
    print(f"  objetos: {len(objs)} | universo enriquecivel: {len(universo)} | faltam: {len(universo) - len(conjunto)}")

    duplicados = sorted({t for t in ids if ids.count(t) > 1})
    fora = [t for t in ids if t not in universo]
    print(f"  duplicados: {duplicados or 'nenhum'}")
    print(f"  fora do universo: {fora or 'nenhum'}")
    if invalidas:
        print(f"  linhas invalidas: {len(invalidas)}")
        for i in invalidas:
            print(f"    ! {i}")

    faltando = buracos(ids, tax)
    if faltando:
        print(f"  buracos ({len(faltando)}): {', '.join(faltando)}")
    else:
        print("  buracos: nenhum (arquivo contiguo)")

    if not objs:
        return 0

    itens = validar(objs, tax, [])
    ok, reprovados = _resumo(itens)
    avisos_total = sum(len(i.avisos) for i in itens)
    print(f"\nContrato: {ok} ok, {reprovados} reprovado(s), {avisos_total} aviso(s)")
    _tabela([i for i in itens if not i.ok or i.avisos])

    if args.csv:
        destino = Path(args.csv)
        with destino.open("w", encoding="utf-8", newline="") as fh:
            fh.write("id_tema,status,mensagens\n")
            for it in itens:
                msgs = it.erros + [f"~ {a}" for a in it.avisos]
                fh.write(f'{it.id},{"ERRO" if it.erros else "ok"},"{" | ".join(msgs)}"\n')
        print(f"\nRelatorio CSV: {destino}")

    return 1 if reprovados else 0


def cmd_proxima(args, tax: Taxonomia) -> int:
    objs, _ = ler_arquivo(Path(args.arquivo))
    ids = [o["id_tema"] for o in objs]
    faltando = buracos(ids, tax)
    if faltando and not args.apos:
        print(f"ATENCAO: o arquivo tem {len(faltando)} buraco(s): {', '.join(faltando)}")
        print(f"  Para fechar o buraco antes: --apos {faltando[0]}\n")
    try:
        rodada = proxima_rodada(ids, tax, n=args.proxima, apos=args.apos)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    _bloco_rodada(rodada, tax)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", default=str(PADRAO), help="JSONL de destino (default: enriquecimento_v01.jsonl)")
    ap.add_argument("--de", help="ler a resposta de um arquivo em vez do stdin")
    ap.add_argument("--commit", action="store_true", help="gravar os objetos validados")
    ap.add_argument("--auditar", action="store_true", help="relatorio do arquivo inteiro")
    ap.add_argument("--proxima", type=int, metavar="N", help="imprimir a proxima rodada com N objetos")
    ap.add_argument("--apos", help="comecar a rodada depois deste id (default: apos o ultimo do arquivo)")
    ap.add_argument("--permitir-buraco", action="store_true", help="gravar mesmo com ids faltando")
    ap.add_argument("--csv", help="salvar o relatorio da auditoria em CSV")
    args = ap.parse_args()

    tax = Taxonomia.carregar()

    if args.auditar:
        return cmd_auditar(args, tax)
    if args.proxima:
        return cmd_proxima(args, tax)
    return cmd_ingerir(args, tax)


if __name__ == "__main__":
    raise SystemExit(main())
