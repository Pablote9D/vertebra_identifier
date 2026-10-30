"""Servidor web: la API de identificación y la página de la app (carpeta web/).

Configuración por variables de entorno:
  INDICE      índice a cargar (por defecto indice.npz)
  ESPECIES    CSV opcional con id_especie, nombre_comun, nombre_cientifico
  UMBRAL_MM   distancia sugerida por `evaluar` para avisar que no hay nada parecido
  MAX_MB      tamaño máximo del archivo subido (por defecto 30; Cloud Run no acepta envíos de más de 32 MB)
  WEB         carpeta de la página (por defecto web/ junto al paquete)

Los archivos subidos se procesan en una carpeta temporal y se borran al terminar.

Uso local:  INDICE=indice.npz uvicorn --factory vertebras.servidor:crear_app --port 8080
"""

import csv
import logging
import os
import tempfile
import threading
import time
from collections import defaultdict

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from scipy.spatial import cKDTree

from .alineacion import alinear_fino, alinear_grueso
from .indice import buscar, cargar_indice, describir_limpieza, preparar_consulta
from .mallas import o3d
from .regiones import REGIONES, codigo, prefijo

EXTENSIONES = (".ply", ".obj", ".stl", ".off")
log = logging.getLogger("vertebras.servidor")
PUNTOS_MAPA = 4000


def _leer_especies(ruta):
    if not ruta or not os.path.isfile(ruta):
        return {}
    with open(ruta, newline="", encoding="utf-8-sig") as fh:
        return {f["id_especie"].strip(): {"nombre_comun": f.get("nombre_comun", "").strip(),
                                          "nombre_cientifico": f.get("nombre_cientifico", "").strip()}
                for f in csv.DictReader(fh)}


def crear_app(indice=None, especies=None, umbral_mm=None, max_mb=None, web=None):
    indice = indice or os.environ.get("INDICE", "indice.npz")
    especies = _leer_especies(especies or os.environ.get("ESPECIES"))
    umbral_mm = umbral_mm if umbral_mm is not None else (
        float(os.environ["UMBRAL_MM"]) if os.environ.get("UMBRAL_MM") else None)
    max_bytes = int((max_mb or float(os.environ.get("MAX_MB", 30))) * 1024 * 1024)
    web = web or os.environ.get("WEB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

    o3d()                               # si a Open3D le falta una librería del sistema, falla al arrancar
    ind = cargar_indice(indice)
    candado = threading.Lock()          # una consulta por vez: cada una ocupa un núcleo entero
    app = FastAPI(title="Identificación de vértebras", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def nombres(esp):
        return especies.get(esp, {"nombre_comun": "", "nombre_cientifico": ""})

    @app.get("/api/salud")
    def salud():
        return {"ok": True, "vertebras": len(ind["etiquetas"])}

    @app.get("/api/coleccion")
    def coleccion():
        grupos = defaultdict(lambda: {"individuos": set(), "vertebras": 0, "regiones": defaultdict(int)})
        for esp, indiv, region, pos, _ in ind["etiquetas"]:
            g = grupos[esp]
            g["individuos"].add(indiv); g["vertebras"] += 1; g["regiones"][region] += 1
        lista = [{"id_especie": esp, **nombres(esp), "individuos": len(g["individuos"]),
                  "vertebras": g["vertebras"], "regiones": dict(g["regiones"]),
                  "evaluable": len(g["individuos"]) >= 2}
                 for esp, g in grupos.items()]
        lista.sort(key=lambda x: (-x["vertebras"], x["id_especie"]))
        regiones = defaultdict(int)
        for e in ind["etiquetas"]:
            regiones[e[2]] += 1
        return {"vertebras": len(ind["etiquetas"]), "individuos": len({e[1] for e in ind["etiquetas"]}),
                "especies": lista,
                "regiones": [{"region": r, "codigo": p, "vertebras": regiones[r]}
                             for r, p in REGIONES.items() if regiones.get(r)]}

    @app.post("/api/identificar")
    def identificar(archivo: UploadFile = File(...), fragmento: bool = Form(False),
                    region: str = Form("")):
        ext = os.path.splitext(archivo.filename or "")[1].lower()
        if ext not in EXTENSIONES:
            raise HTTPException(422, f"Formato no admitido ({ext or 'sin extensión'}). Usá PLY, OBJ, STL u OFF.")
        if region:
            try:
                prefijo(region)
            except ValueError as e:
                raise HTTPException(422, str(e)) from None
        with tempfile.TemporaryDirectory() as carpeta:      # el archivo se borra al salir
            ruta = os.path.join(carpeta, "consulta" + ext)
            total = 0
            with open(ruta, "wb") as fh:
                while bloque := archivo.file.read(1024 * 1024):
                    total += len(bloque)
                    if total > max_bytes:
                        raise HTTPException(413, f"El archivo supera los {max_bytes // (1024 * 1024)} MB.")
                    fh.write(bloque)
            t0 = time.time()
            with candado:
                info = {}
                try:
                    q = preparar_consulta(ruta, limpiar=True, info=info)
                except Exception:                         # noqa: BLE001 - cualquier falla de lectura
                    log.exception("No se pudo preparar la consulta %s", archivo.filename)
                    raise HTTPException(422, "No se pudo leer la malla. Revisá que sea un archivo 3D válido.") from None
                try:
                    res = buscar(q, ind, top=5, fragmento=fragmento, region=region or None)
                except ValueError as e:
                    raise HTTPException(422, str(e)) from None
                mapa = _mapa_diferencias(q, res[0], ind)
        mejor = res[0][1]
        return {
            "candidatas": [{"id_especie": esp, **nombres(esp), "region": reg, "posicion": int(pos),
                            "codigo": codigo(reg, pos), "distancia_mm": round(float(d), 4),
                            "probabilidad": round(float(p), 4), "individuo": indiv}
                           for (esp, reg, pos), d, indiv, p in res],
            "umbral_mm": umbral_mm,
            "supera_umbral": bool(umbral_mm is not None and mejor > umbral_mm),
            "tamano_mm": [round(float(x), 1) for x in np.ptp(q, axis=0)],
            "limpieza": describir_limpieza(info),
            "fragmento": fragmento,
            "comparadas": len(ind["etiquetas"]) if not region else
                          sum(prefijo(e[2]) == prefijo(region) for e in ind["etiquetas"]),
            "mapa": mapa,
            "segundos": round(time.time() - t0, 1),
        }

    if os.path.isdir(web):
        app.mount("/", StaticFiles(directory=web, html=True), name="web")
    return app


def _mapa_diferencias(q, mejor, ind):
    """Puntos de la consulta alineados con la mejor referencia y su distancia a ella (mm),
    más una muestra de la referencia, para dibujar dónde difieren."""
    (esp, reg, pos), _, indiv, _ = mejor
    i = next(k for k, e in enumerate(ind["etiquetas"]) if (e[0], e[1], e[2], e[3]) == (esp, indiv, reg, pos))
    ref = ind["puntos"][i]
    _, tr = alinear_grueso(q, ref, ind["normales"][i], ind["cache"][i])
    r, t = alinear_fino(q, ref, tr, ind["normales"][i], ind["cache"][i])
    qa = (q @ r.T + t)[:PUNTOS_MAPA]
    d = cKDTree(ref).query(qa)[0]
    redondear = lambda a: np.round(a, 2).tolist()  # noqa: E731
    return {"consulta": redondear(qa), "distancias": redondear(d),
            "referencia": redondear(ref[:PUNTOS_MAPA // 2])}

