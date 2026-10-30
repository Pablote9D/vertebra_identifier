"""
Identificación de vértebras de aves por comparación de modelos 3D.

Subcomandos:
  sintetico    Genera una base de prueba con vértebras 3D sintéticas.
  indexar      Procesa la base (metadata.csv + mallas) y guarda un índice.
  identificar  Compara un modelo 3D contra el índice y muestra candidatas.
  evaluar      Prueba "dejando un individuo afuera" y mide la precisión.

Uso: python -m vertebras <subcomando> [opciones]
"""

import argparse
import os
import sys

from . import config as cfg
from .evaluacion import evaluar
from .indice import cargar_indice, describir_limpieza, identificar, indexar
from .regiones import codigo
from .sintetico import generar_base


def cmd_sintetico(args):
    n = generar_base(args.salida, args.individuos, args.semilla)
    print(f"{n} vértebras sintéticas en {args.salida}")


def cmd_indexar(args):
    n = indexar(args.metadata, args.salida, avisar=lambda a: print(f"  {a}", file=sys.stderr),
                limpiar=args.limpiar)
    print(f"Índice con {n} vértebras guardado en {args.salida}")


def _configurar(args):
    cfg.configurar(args.motor, args.icp, args.orientaciones)


def cmd_identificar(args):
    _configurar(args)
    info = {}
    res = identificar(args.modelo, cargar_indice(args.indice), top=args.top, limpiar=args.limpiar, info=info)
    print(f"\nCandidatas para {os.path.basename(args.modelo)}:\n")
    if describir_limpieza(info):
        print(f"  Limpieza: {describir_limpieza(info)}\n")
    print(f"  {'Especie':<10}{'Posición':<10}{'Prob. rel.':>11}{'Dist. (mm)':>12}  Individuo más parecido")
    for (esp, reg, pos), dist, indiv, p in res:
        print(f"  {esp:<10}{codigo(reg, pos):<10}{p:>10.0%}{dist:>12.3f}  {indiv}")
    if args.umbral and res[0][1] > args.umbral:
        print(f"\n  Atención: la mejor distancia ({res[0][1]:.3f} mm) supera el umbral "
              f"({args.umbral} mm). Puede no haber nada parecido en la base.")
    print("\n  La probabilidad es relativa entre candidatas, todavía no está calibrada.")


def cmd_evaluar(args):
    _configurar(args)
    r = evaluar(args.indice, recorte=args.recorte, muestra=args.muestra, nucleos=args.nucleos)
    motor = cfg.MOTOR + (f"/{cfg.ICP}" if cfg.MOTOR == "open3d" else "")
    print(f"\nEvaluación dejando un individuo afuera ({r['total']} vértebras, "
          f"recorte {r['recorte']:.0%}, {cfg.N_ORIENTACIONES} orientaciones, motor {motor}, "
          f"{r['nucleos']} núcleos, {r['segundos']:.0f} s)\n")
    print(f"  Especie correcta:            {r['especie']:6.1%}")
    print(f"  Posición exacta:             {r['exacta']:6.1%}")
    print(f"  Posición con error ±1:       {r['mas_menos1']:6.1%}")
    print(f"  Correcta entre las 3 primeras: {r['top3']:4.1%}")
    if r["errores"]:
        print("  Errores mayores a 1 posición: " +
              ", ".join(f"{k} posiciones: {v}" for k, v in r["errores"].items()))
    if r["umbral_sugerido"] is not None:
        print(f"\n  Umbral sugerido para 'no se parece a nada': {r['umbral_sugerido']:.3f} mm")
    if r["sin_referencia"]:
        print(f"\n  No se contaron {len(r['sin_referencia'])} vértebras sin otro individuo de su especie "
              "y posición en la base: " + ", ".join(f"{e[1]} {codigo(e[2], e[3])}" for e in r["sin_referencia"][:8])
              + (", ..." if len(r["sin_referencia"]) > 8 else ""))
    print(f"\n  Por posición:\n\n  {'Posición':<10}{'Consultas':>9}{'Exacta':>8}{'±1':>7}  Predicciones (posición elegida × veces)")
    for (reg, pos), pp in r["por_posicion"].items():
        preds = ", ".join(f"{k} ×{v}" for k, v in pp["predicciones"].most_common())
        print(f"  {codigo(reg, pos):<10}{pp['n']:>9}{pp['exacta'] / pp['n']:>8.0%}{pp['mas_menos1'] / pp['n']:>7.0%}  {preds}")


AYUDA_LIMPIAR = ("quitar piezas sueltas ajenas a la vértebra (marcadores, restos de segmentación); "
                 "informa cuánto se quitó de cada malla")


def _opciones_motor(s):
    s.add_argument("--orientaciones", type=int, choices=(4, 24), default=cfg.N_ORIENTACIONES,
                   help="orientaciones iniciales de la alineación rápida")
    s.add_argument("--motor", choices=("open3d", "scipy"), default=cfg.MOTOR, help="implementación del ICP")
    s.add_argument("--icp", choices=("punto", "plano"), default=cfg.ICP,
                   help="con --motor open3d: ICP punto a punto o punto a plano")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m vertebras", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sintetico", help="generar base de prueba")
    s.add_argument("--salida", default="base_sintetica")
    s.add_argument("--individuos", type=int, default=4)
    s.add_argument("--semilla", type=int, default=42)
    s.set_defaults(func=cmd_sintetico)

    s = sub.add_parser("indexar", help="procesar la base")
    s.add_argument("--metadata", required=True)
    s.add_argument("--salida", default="indice.npz")
    s.add_argument("--limpiar", action="store_true", help=AYUDA_LIMPIAR)
    s.set_defaults(func=cmd_indexar)

    s = sub.add_parser("identificar", help="identificar una vértebra")
    s.add_argument("modelo")
    s.add_argument("--indice", default="indice.npz")
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--umbral", type=float, default=None, help="distancia en mm (sale de 'evaluar')")
    s.add_argument("--limpiar", action="store_true", help=AYUDA_LIMPIAR)
    _opciones_motor(s)
    s.set_defaults(func=cmd_identificar)

    s = sub.add_parser("evaluar", help="medir precisión dejando un individuo afuera")
    s.add_argument("--indice", default="indice.npz")
    s.add_argument("--recorte", type=float, default=0.0,
                   help="fracción a eliminar de cada consulta para simular fragmentos (ej. 0.3)")
    s.add_argument("--muestra", type=int, default=0,
                   help="evaluar solo N vértebras al azar (más rápido)")
    s.add_argument("--nucleos", type=int, default=0,
                   help="procesos en paralelo (por defecto, todos los núcleos)")
    _opciones_motor(s)
    s.set_defaults(func=cmd_evaluar)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
