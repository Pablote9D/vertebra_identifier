"""Evaluación dejando un individuo afuera, repartida en varios procesos."""

import os
import time
from collections import Counter, defaultdict

import numpy as np

from . import config as cfg
from .indice import buscar, cargar_indice
from .preproceso import a_marco_pca, descriptor, recortar
from .regiones import REGIONES, codigo, prefijo

_EVAL = {}


def _iniciar_trabajador(ruta_indice, recorte, motor, icp, orientaciones, indice=None):
    """Prepara un proceso de evaluación: carga el índice y fija la configuración."""
    cfg.configurar(motor, icp, orientaciones)
    _EVAL["ind"] = indice if indice is not None else cargar_indice(ruta_indice)
    _EVAL["recorte"] = recorte


def _evaluar_consulta(i):
    """Busca la vértebra i dejando afuera a su individuo. Cada consulta tiene su propia semilla,
    así el resultado no depende del orden ni de la cantidad de núcleos."""
    ind = _EVAL["ind"]
    e = ind["etiquetas"][i]
    q = ind["puntos"][i]
    rng = np.random.default_rng(1000 + i)
    if _EVAL["recorte"] > 0:
        q = a_marco_pca(recortar(q, _EVAL["recorte"], rng)).astype(np.float32)
    return i, buscar(q, descriptor(q, rng), ind, excluir=e[1], top=3)


def evaluar(ruta_indice, recorte=0.0, muestra=0, nucleos=0):
    """Deja afuera un individuo entero por vez y trata de ubicar sus vértebras con el resto.
    Las consultas cuya especie y posición no aparecen en ningún otro individuo no tienen respuesta
    posible: no se cuentan y se informan en "sin_referencia".
    Devuelve un diccionario con las métricas, el resumen por posición y el detalle por consulta."""
    rng = np.random.default_rng(2)
    ind = cargar_indice(ruta_indice)
    total = esp_ok = exacta = mas_menos1 = top3 = 0
    dist_aciertos = []
    errores = defaultdict(int)
    detalle = []
    por_posicion = {}
    t0 = time.time()
    individuos = defaultdict(set)                  # (especie, región, posición) -> individuos
    for e in ind["etiquetas"]:
        individuos[(e[0], e[2], e[3])].add(e[1])
    consultas, sin_referencia = [], []
    for i, e in enumerate(ind["etiquetas"]):
        (consultas if individuos[(e[0], e[2], e[3])] - {e[1]} else sin_referencia).append(i)
    if not consultas:
        raise ValueError("Ninguna vértebra tiene en la base otro individuo de su especie y posición")
    if muestra and muestra < len(consultas):
        consultas = [int(i) for i in sorted(rng.choice(consultas, muestra, replace=False))]
    config = (ruta_indice, recorte, cfg.MOTOR, cfg.ICP, cfg.N_ORIENTACIONES)
    nucleos = max(1, min(nucleos or os.cpu_count() or 1, len(consultas)))
    pool = None
    if nucleos == 1:
        _iniciar_trabajador(*config, indice=ind)
        resultados = map(_evaluar_consulta, consultas)
    else:
        import multiprocessing as mp
        # cada proceso usa un solo hilo, para no competir por los núcleos
        for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(var, "1")
        pool = mp.get_context("spawn").Pool(nucleos, _iniciar_trabajador, config)
        resultados = pool.imap(_evaluar_consulta, consultas)
    try:
        for i, res in resultados:
            e = ind["etiquetas"][i]
            (esp, reg, pos) = res[0][0]
            total += 1
            if esp == e[0]:
                esp_ok += 1
                if reg == e[2] and pos == e[3]:
                    exacta += 1; dist_aciertos.append(res[0][1])
                if reg == e[2] and abs(pos - e[3]) <= 1:
                    mas_menos1 += 1
                elif reg == e[2]:
                    errores[abs(pos - e[3])] += 1
            if any(r[0] == (e[0], e[2], e[3]) for r in res):
                top3 += 1
            detalle.append({"consulta": e, "candidatas": res})
            pp = por_posicion.setdefault((e[2], e[3]), {"n": 0, "exacta": 0, "mas_menos1": 0,
                                                       "predicciones": Counter()})
            pp["n"] += 1
            if esp == e[0]:
                pp["exacta"] += reg == e[2] and pos == e[3]
                pp["mas_menos1"] += reg == e[2] and abs(pos - e[3]) <= 1
                pp["predicciones"][codigo(reg, pos)] += 1
            else:
                pp["predicciones"]["otra especie"] += 1
    finally:
        if pool is not None:
            pool.close(); pool.join()
    return {
        "total": total, "recorte": recorte, "nucleos": nucleos, "segundos": time.time() - t0,
        "especie": esp_ok / total, "exacta": exacta / total, "mas_menos1": mas_menos1 / total,
        "top3": top3 / total, "errores": dict(sorted(errores.items())),
        "umbral_sugerido": (np.percentile(dist_aciertos, 95) * 1.5 if dist_aciertos else None),
        "por_posicion": dict(sorted(por_posicion.items(), key=lambda kv: _orden_posicion(*kv[0]))),
        "sin_referencia": [ind["etiquetas"][i] for i in sin_referencia],
        "detalle": detalle,
    }


def _orden_posicion(region, pos):
    """Orden anatómico: por región (cervical a pigóstilo) y número."""
    return list(REGIONES.values()).index(prefijo(region)), pos
