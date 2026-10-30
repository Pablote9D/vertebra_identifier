"""Base de prueba con vértebras sintéticas.

Las formas son muy simplificadas, y simétricas izquierda-derecha y también craneal-caudal
(las reales no lo son en este último sentido). Sirven para verificar que todo funciona,
no para predecir la precisión con huesos reales."""

import csv
import os

import numpy as np

from .mallas import escribir_ply


def _caja(centro, tam):
    cx, cy, cz = centro; sx, sy, sz = np.asarray(tam) / 2
    v = np.array([[cx + a * sx, cy + b * sy, cz + c * sz]
                  for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)])
    f = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
         [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]]
    return v, np.array(f)


def _cilindro(centro, rx, ry, largo, eje="z", seg=24):
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    anillo = np.c_[rx * np.cos(ang), ry * np.sin(ang)]
    z0, z1 = -largo / 2, largo / 2
    v = np.vstack([np.c_[anillo, np.full(seg, z0)], np.c_[anillo, np.full(seg, z1)],
                   [[0, 0, z0], [0, 0, z1]]])
    f = []
    for k in range(seg):
        a, b = k, (k + 1) % seg
        f += [[a, b, seg + b], [a, seg + b, seg + a],
              [2 * seg, b, a], [2 * seg + 1, seg + a, seg + b]]
    if eje == "x":
        v = v[:, [2, 1, 0]]
    return v + np.asarray(centro), np.array(f)


def vertebra_sintetica(t, sp, iv, rng):
    """Vértebra cervical simplificada cuya forma cambia gradualmente con la posición t (0 a 1)."""
    S = sp["tam"] * iv["escala"]
    m = lambda k: iv[k] * rng.normal(1, 0.03)           # variación individual + de pieza
    L = S * (0.55 + sp["largo"] * np.sin(np.pi * t) ** 0.8) * m("a")
    rx, ry = S * 0.2 * (1 + 0.7 * t) * m("b"), S * 0.15 * (1 + 0.4 * t) * m("b")
    espina = S * (0.35 * np.exp(-((t - 0.05) / 0.15) ** 2) + sp["espina"] * t ** 3 + 0.04) * m("c")
    arco = S * 0.22 * (1 + 0.3 * t) * m("d")
    zyg = S * 0.22 * (1 + 0.6 * np.sin(np.pi * t)) * m("e")
    trans = S * 0.25 * (0.4 + 1.2 * t) * m("f")
    ventral = S * 0.3 * (np.exp(-(t / 0.12) ** 2) + max(0.0, t - 0.75) * 3) * m("g")
    partes = [
        _cilindro((0, 0, 0), rx, ry, L),
        _caja((0, ry + arco / 2, 0), (rx * 2.2, arco, L * 0.8)),
        _caja((0, ry + arco + espina / 2, 0), (rx * 0.4, espina, L * 0.4)),
        _caja((0, -ry * 0.3, 0), (rx * 2 + trans * 2, ry * 0.6, L * 0.5)),
    ]
    for lado in (-1, 1):
        for sent in (-1, 1):
            partes.append(_cilindro((lado * rx * 0.9, ry + arco * 0.6, sent * (L / 2 + zyg / 2 - L * 0.15)),
                                    rx * 0.25, rx * 0.18, zyg))
    if ventral > S * 0.02:
        partes.append(_caja((0, -ry - ventral / 2, 0), (rx * 0.35, ventral, L * 0.5)))
    vs, fs, off = [], [], 0
    for v, f in partes:
        vs.append(v); fs.append(f + off); off += len(v)
    v = np.vstack(vs)
    # posición y orientación arbitrarias, como en un escaneo real
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return v @ q.T + rng.normal(0, 20, 3), np.vstack(fs)


def generar_base(salida, individuos=4, semilla=42):
    """Genera 3 especies con `individuos` individuos cada una y su metadata.csv.
    Devuelve la cantidad de vértebras."""
    rng = np.random.default_rng(semilla)
    especies = {
        "ESPAAA": {"n": 13, "tam": 12, "largo": 0.9, "espina": 0.30},
        "ESPBBB": {"n": 15, "tam": 14, "largo": 1.1, "espina": 0.25},
        "ESPCCC": {"n": 15, "tam": 15, "largo": 1.0, "espina": 0.40},  # parecida a B a propósito
    }
    os.makedirs(os.path.join(salida, "mallas"), exist_ok=True)
    filas = []
    for esp, sp in especies.items():
        for k in range(individuos):
            indiv = f"{esp}-{k + 1:03d}"
            iv = {"escala": rng.normal(1, 0.07), **{c: rng.normal(1, 0.06) for c in "abcdefg"}}
            for pos in range(1, sp["n"] + 1):
                t = (pos - 1) / (sp["n"] - 1)
                v, f = vertebra_sintetica(t, sp, iv, rng)
                nombre = f"mallas/{esp}_{indiv}_C{pos:02d}_v1.ply"
                escribir_ply(os.path.join(salida, nombre), v, f)
                filas.append({"id_escaneo": f"{indiv}-C{pos:02d}", "archivo_liviano": nombre,
                              "id_especie": esp, "id_individuo": indiv, "region": "Cervical",
                              "posicion": pos, "aprobado": "Sí"})
    with open(os.path.join(salida, "metadata.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    return len(filas)
