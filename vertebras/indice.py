"""Índice de referencia: construirlo a partir de metadata.csv, cargarlo y consultarlo."""

import csv
import os

import numpy as np

from . import config as cfg
from .alineacion import alinear_grueso, comparar_fino
from .preproceso import preparar
from .regiones import prefijo


def leer_metadata(ruta):
    """Filas aprobadas de metadata.csv, con la ruta de la malla resuelta y la región validada."""
    base = os.path.dirname(os.path.abspath(ruta))
    with open(ruta, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    validas = []
    for num, fila in enumerate(filas, start=2):            # fila 1 = encabezado
        if fila.get("aprobado", "Sí").strip().lower() in ("no", "false", "0"):
            continue
        try:
            prefijo(fila["region"])
            int(fila["posicion"])
        except (KeyError, ValueError) as e:
            raise ValueError(f"{ruta}, fila {num}: {e}") from None
        validas.append({**fila, "ruta": os.path.join(base, fila["archivo_liviano"])})
    return validas


def describir_limpieza(info):
    """Texto para informar la limpieza de una malla, o "" si no se quitó nada apreciable."""
    q = info.get("area_quitada", 0.0)
    if q <= 0.001:
        return ""
    n = info["piezas_quitadas"]
    texto = f"se quitó {q:.1%} del área ({n} {'pieza suelta' if n == 1 else 'piezas sueltas'})"
    return texto + (" — revisar la malla" if q > 0.05 else "")


def indexar(metadata, salida, avisar=None, limpiar=False):
    """Procesa las mallas de metadata.csv y guarda el índice. Devuelve la cantidad de vértebras.
    Con limpiar=True quita las piezas ajenas de cada malla (ver preproceso.limpiar_piezas)."""
    rng = np.random.default_rng(0)
    puntos, normales, descs, etiquetas = [], [], [], []
    for fila in leer_metadata(metadata):
        info = {}
        p, n, d = preparar(fila["ruta"], rng, normales=True, limpiar=limpiar, info=info)
        puntos.append(p); normales.append(n); descs.append(d)
        etiquetas.append((fila["id_especie"], fila["id_individuo"], fila["region"],
                          int(fila["posicion"]), fila.get("id_escaneo", "")))
        if avisar:
            limpieza = describir_limpieza(info)
            avisar(fila["archivo_liviano"] + (f": {limpieza}" if limpieza else ""))
    if not puntos:
        raise ValueError(f"No hay vértebras aprobadas en {metadata}")
    descs = np.array(descs)
    np.savez_compressed(salida, puntos=np.array(puntos, dtype=object),
                        normales=np.array(normales, dtype=object),
                        descs=descs, media=descs.mean(0), desv=descs.std(0) + 1e-9,
                        etiquetas=np.array(etiquetas, dtype=object))
    return len(puntos)


def cargar_indice(ruta):
    z = np.load(ruta, allow_pickle=True)
    puntos = [np.asarray(x, dtype=np.float64) for x in z["puntos"]]
    # los índices viejos no tienen normales: se estiman al usarlas
    normales = ([np.asarray(x, dtype=np.float64) for x in z["normales"]] if "normales" in z.files
                else [None] * len(puntos))
    return {"puntos": puntos, "normales": normales, "descs": z["descs"], "media": z["media"],
            "desv": z["desv"], "etiquetas": [tuple(e) for e in z["etiquetas"]],
            "cache": [dict() for _ in puntos]}


def buscar(q, dq, ind, excluir=None, top=5):
    """Devuelve las candidatas: (especie, región, posición), distancia, individuo, prob. relativa."""
    validos = [i for i, e in enumerate(ind["etiquetas"]) if excluir is None or e[1] != excluir]
    if len(validos) > cfg.MAX_SIN_PRESELECCION:
        z = (ind["descs"][validos] - ind["media"]) / ind["desv"]
        zq = (dq - ind["media"]) / ind["desv"]
        validos = [validos[o] for o in np.argsort(np.linalg.norm(z - zq, axis=1))[:cfg.N_PRESELECCION]]
    gruesos = [alinear_grueso(q, ind["puntos"][i], ind["normales"][i], ind["cache"][i]) + (i,)
               for i in validos]
    gruesos.sort(key=lambda x: x[0])
    por_etiqueta = {}
    for _, transf, i in gruesos[:cfg.N_FINALISTAS]:
        dist = comparar_fino(q, ind["puntos"][i], transf, ind["normales"][i], ind["cache"][i])
        e = ind["etiquetas"][i]
        clave = (e[0], e[2], e[3])                      # especie, región, posición
        if dist < por_etiqueta.get(clave, (np.inf,))[0]:
            por_etiqueta[clave] = (dist, e[1])
    res = sorted(((k, v[0], v[1]) for k, v in por_etiqueta.items()), key=lambda x: x[1])
    d = np.array([r[1] for r in res])
    # si la consulta coincide exactamente con una referencia, d[0] es 0
    pesos = np.exp(-((d / max(d[0], 1e-9)) ** 2 - 1) * 6)
    prob = pesos / pesos.sum()
    return [(r[0], r[1], r[2], p) for r, p in zip(res, prob)][:top]


def identificar(ruta_modelo, ind, top=5, limpiar=False, info=None):
    """Candidatas para un modelo 3D (mismo formato que `buscar`). Con limpiar=True quita antes
    las piezas ajenas, y anota en `info` cuánto se quitó."""
    rng = np.random.default_rng(1)
    q, dq = preparar(ruta_modelo, rng, limpiar=limpiar, info=info)
    return buscar(q.astype(np.float64), dq, ind, top=top)
