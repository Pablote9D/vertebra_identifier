"""Revisión de una base antes de indexar: planilla, archivos y mallas.

Junta todos los problemas en lugar de frenar en el primero. Cada problema tiene un nivel:
  error  impide indexar (archivo que falta, región desconocida, malla ilegible...)
  aviso  conviene revisarlo (unidades sospechosas, piezas sueltas, posición repetida...)
  info   para saber (posiciones faltantes, especies con un solo individuo...)
"""

import csv
import os
from collections import defaultdict

import numpy as np

from .mallas import leer_malla
from .preproceso import ejes_pca, limpiar_piezas
from .regiones import codigo, prefijo

COLUMNAS = ("id_escaneo", "archivo_liviano", "id_especie", "id_individuo", "region", "posicion", "aprobado")
_APROBADO = {"sí": True, "si": True, "yes": True, "true": True, "1": True,
             "no": False, "false": False, "0": False}

LARGO_MIN_MM = 1.0       # más chico que esto, probablemente no está en mm
LARGO_MAX_MM = 200.0     # más grande que esto, probablemente no está en mm
CARAS_MIN = 2000
CARAS_MAX = 1_500_000
RAZON_TAMANO = 1.6       # entre individuos de la misma especie y posición


def verificar(metadata, leer_mallas=True, avisar=None):
    """Revisa metadata.csv y sus mallas. Devuelve {"problemas": [...], "resumen": {...}}.
    Cada problema es {"nivel", "fila", "id", "mensaje"}; `fila` es la fila de la planilla
    (1 = encabezado) o None si el problema es de un individuo o especie."""
    problemas = []

    def anotar(nivel, mensaje, fila=None, ident=""):
        problemas.append({"nivel": nivel, "fila": fila, "id": ident, "mensaje": mensaje})

    base = os.path.dirname(os.path.abspath(metadata))
    with open(metadata, newline="", encoding="utf-8-sig") as fh:
        lector = csv.DictReader(fh)
        faltan = [c for c in COLUMNAS if c not in (lector.fieldnames or [])]
        filas = list(lector)
    if faltan:
        anotar("error", f"Faltan columnas en la planilla: {', '.join(faltan)}")
        return {"problemas": problemas, "resumen": {"filas": len(filas)}}

    validas = []                                # (num, fila, posición) aprobadas y bien escritas
    ids = defaultdict(list)
    especie_de = {}
    for num, fila in enumerate(filas, start=2):
        ident = fila["id_escaneo"].strip() or f"fila {num}"
        aprob = _APROBADO.get(fila["aprobado"].strip().lower())
        if aprob is None:
            anotar("aviso", f"Valor de 'aprobado' no reconocido ({fila['aprobado']!r}); se toma como Sí",
                   num, ident)
        if aprob is False:
            continue
        ok = True
        for col in ("id_escaneo", "archivo_liviano", "id_especie", "id_individuo"):
            if not fila[col].strip():
                anotar("error", f"Columna '{col}' vacía", num, ident); ok = False
        try:
            prefijo(fila["region"])
        except ValueError as e:
            anotar("error", str(e), num, ident); ok = False
        try:
            pos = int(fila["posicion"])
        except ValueError:
            anotar("error", f"Posición no es un número entero: {fila['posicion']!r}", num, ident); ok = False
        if fila["archivo_liviano"].strip() and not os.path.isfile(os.path.join(base, fila["archivo_liviano"])):
            anotar("error", f"No existe el archivo {fila['archivo_liviano']}", num, ident); ok = False
        indiv, esp = fila["id_individuo"].strip(), fila["id_especie"].strip()
        if indiv and especie_de.setdefault(indiv, esp) != esp:
            anotar("error", f"El individuo {indiv} figura con dos especies: {especie_de[indiv]} y {esp}",
                   num, ident); ok = False
        ids[fila["id_escaneo"].strip()].append(num)
        if ok:
            validas.append((num, fila, pos))

    for ident, nums in ids.items():
        if ident and len(nums) > 1:
            anotar("aviso", f"id_escaneo repetido en las filas {', '.join(map(str, nums))}", nums[0], ident)
    por_lugar = defaultdict(list)
    for num, fila, pos in validas:
        por_lugar[(fila["id_individuo"].strip(), prefijo(fila["region"]), pos)].append(num)
    for (indiv, pref, pos), nums in por_lugar.items():
        if len(nums) > 1:
            anotar("aviso", f"{indiv} tiene {pref}{pos:02d} en varias filas ({', '.join(map(str, nums))})",
                   nums[0], indiv)

    # posiciones faltantes dentro de cada región, por individuo
    posiciones = defaultdict(set)
    for num, fila, pos in validas:
        posiciones[(fila["id_individuo"].strip(), fila["region"].strip())].add(pos)
    for (indiv, region), ps in sorted(posiciones.items()):
        huecos = sorted(set(range(min(ps), max(ps) + 1)) - ps)
        if huecos:
            anotar("info", "Faltan posiciones entre la primera y la última de la región: "
                           + ", ".join(codigo(region, p) for p in huecos), None, indiv)

    individuos = defaultdict(set)
    for num, fila, pos in validas:
        individuos[fila["id_especie"].strip()].add(fila["id_individuo"].strip())
    for esp, inds in sorted(individuos.items()):
        if len(inds) == 1:
            anotar("info", "Especie con un solo individuo: sus vértebras no se pueden evaluar "
                           "dejando un individuo afuera", None, esp)

    largos = {}
    if leer_mallas:
        for num, fila, pos in validas:
            ident = fila["id_escaneo"].strip()
            if avisar:
                avisar(fila["archivo_liviano"])
            largo = _revisar_malla(os.path.join(base, fila["archivo_liviano"]), num, ident, anotar)
            if largo is not None:
                largos[num] = (fila["id_especie"].strip(), fila["id_individuo"].strip(),
                               prefijo(fila["region"]), pos, largo)
        _revisar_tamanos(largos, anotar)

    resumen = {"filas": len(filas), "aprobadas": len(validas),
               "especies": len(individuos), "individuos": len(especie_de),
               **{nivel: sum(p["nivel"] == nivel for p in problemas) for nivel in ("error", "aviso", "info")}}
    problemas.sort(key=lambda p: (("error", "aviso", "info").index(p["nivel"]), p["fila"] or 0))
    return {"problemas": problemas, "resumen": resumen}


def _piezas(n):
    return "1 pieza suelta" if n == 1 else f"{n} piezas sueltas"


def _revisar_malla(ruta, num, ident, anotar):
    """Revisa una malla. Devuelve su largo mayor (mm, después de quitar piezas sueltas) o None."""
    try:
        v, f = leer_malla(ruta)
    except Exception as e:                      # noqa: BLE001 - cualquier falla de lectura se informa
        anotar("error", f"No se pudo leer la malla: {e}", num, ident)
        return None
    if f is None:
        anotar("aviso", "El archivo no tiene caras (es una nube de puntos): las normales se estiman "
                        "y no se pueden quitar piezas sueltas", num, ident)
    else:
        if len(f) < CARAS_MIN:
            anotar("aviso", f"Pocas caras ({len(f)}): la superficie puede quedar muy simplificada", num, ident)
        elif len(f) > CARAS_MAX:
            anotar("info", f"Malla muy pesada ({len(f)} caras); la versión liviana alcanza", num, ident)
        v, f, quitada, piezas = limpiar_piezas(v, f)
        if quitada > 0.05:
            anotar("aviso", f"{quitada:.1%} del área está en {_piezas(piezas)} (marcadores, restos o "
                            "una pieza partida); usar --limpiar al indexar y revisar la malla", num, ident)
        elif quitada > 0.001:
            anotar("info", f"{quitada:.1%} del área en {_piezas(piezas)}; --limpiar las quita", num, ident)
    centro, vec = ejes_pca(v)
    largo = float(np.ptp((v - centro) @ vec[:, 0]))
    if largo < LARGO_MIN_MM:
        anotar("aviso", f"Mide {largo:.3g} de largo: demasiado chica para estar en mm "
                        "(¿está en cm o en metros?)", num, ident)
    elif largo > LARGO_MAX_MM:
        anotar("aviso", f"Mide {largo:.4g} de largo: demasiado grande para estar en mm "
                        "(¿está en micrómetros o décimas de mm?)", num, ident)
    return largo


def _revisar_tamanos(largos, anotar):
    """Compara el largo de cada vértebra con el de otros individuos de su especie y posición."""
    grupos = defaultdict(list)
    for num, (esp, indiv, pref, pos, largo) in largos.items():
        grupos[(esp, pref, pos)].append((num, indiv, largo))
    razones = defaultdict(list)                 # individuo -> razones contra los demás
    sueltas = []                                # vértebras de tamaño raro: (individuo, num, mensaje)
    otros_indiv = defaultdict(set)
    for (esp, pref, pos), items in grupos.items():
        for num, indiv, largo in items:
            otros = [l for n, i, l in items if i != indiv]
            otros_indiv[indiv] |= {i for n, i, l in items if i != indiv}
            if not otros:
                continue
            # con 3 o más individuos, la mediana de todos no se deja arrastrar por uno mal escalado
            ref = np.median([l for n, i, l in items]) if len(otros) >= 2 else otros[0]
            r = largo / ref
            razones[indiv].append(r)
            if not 1 / RAZON_TAMANO < r < RAZON_TAMANO:
                sueltas.append((indiv, num, f"Mide {r:.2f} veces lo que miden las {pref}{pos:02d} de otros "
                                            f"individuos de {esp}: ¿posición, especie o unidades equivocadas?"))
    en_otra_unidad = set()
    for indiv, rs in razones.items():
        r = float(np.median(rs))
        if len(rs) >= 3 and not 1 / RAZON_TAMANO < r < RAZON_TAMANO:
            en_otra_unidad.add(indiv)
            duda = (" Con solo dos individuos no se puede saber cuál de los dos está mal."
                    if len(otros_indiv[indiv]) == 1 else "")
            anotar("aviso", f"Sus vértebras miden en general {r:.2f} veces lo de otros individuos de su especie: "
                            f"probablemente esté en otra unidad (si fuera cm daría ~0.1).{duda}", None, indiv)
    for indiv, num, mensaje in sueltas:         # las de un individuo en otra unidad ya están avisadas
        if indiv not in en_otra_unidad:
            anotar("aviso", mensaje, num, indiv)
