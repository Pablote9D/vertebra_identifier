#!/usr/bin/env python3
"""
Prototipo de identificación de vértebras por comparación de modelos 3D.

Subcomandos:
  sintetico    Genera una base de prueba con vértebras 3D sintéticas.
  indexar      Procesa la base (metadata.csv + mallas) y guarda un índice.
  identificar  Compara un modelo 3D contra el índice y muestra candidatas.
  evaluar      Prueba "dejando un individuo afuera" y mide la precisión.

Requiere: numpy, scipy. Opcional: trimesh (para leer más formatos de malla).
"""

import argparse
import csv
import os
import struct
import sys
import time
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

N_DENSO = 15000          # puntos muestreados por modelo (para medir distancias finas)
N_GRUESO = 300           # puntos usados en la etapa rápida de alineación
N_FINO = 2000            # puntos usados en la alineación fina
N_FINALISTAS = 12        # candidatas que pasan a la etapa fina
MAX_SIN_PRESELECCION = 400   # con bases más grandes se preselecciona con un descriptor barato
N_PRESELECCION = 150
RECORTE_ICP = 0.9        # fracción de pares más cercanos usados en cada paso del ICP


# ---------------------------------------------------------------------------
# Lectura y escritura de mallas
# ---------------------------------------------------------------------------

def leer_malla(ruta):
    """Devuelve (vertices Nx3, caras Mx3 o None)."""
    try:
        import trimesh  # noqa: F401
        m = trimesh.load(ruta, force="mesh", process=False)
        caras = np.asarray(m.faces) if len(getattr(m, "faces", [])) else None
        return np.asarray(m.vertices, dtype=float), caras
    except ImportError:
        pass
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".obj":
        return _leer_obj(ruta)
    if ext == ".ply":
        return _leer_ply(ruta)
    raise ValueError(f"Formato no soportado sin trimesh: {ruta}")


def _leer_obj(ruta):
    v, f = [], []
    with open(ruta, encoding="utf-8", errors="ignore") as fh:
        for linea in fh:
            p = linea.split()
            if not p:
                continue
            if p[0] == "v":
                v.append([float(x) for x in p[1:4]])
            elif p[0] == "f":
                idx = [int(x.split("/")[0]) for x in p[1:]]
                idx = [i - 1 if i > 0 else len(v) + i for i in idx]
                for k in range(1, len(idx) - 1):          # triangula polígonos
                    f.append([idx[0], idx[k], idx[k + 1]])
    return np.array(v, float), (np.array(f, int) if f else None)


_TIPOS_PLY = {"char": "b", "int8": "b", "uchar": "B", "uint8": "B",
              "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
              "int": "i", "int32": "i", "uint": "I", "uint32": "I",
              "float": "f", "float32": "f", "double": "d", "float64": "d"}


def _leer_ply(ruta):
    with open(ruta, "rb") as fh:
        if fh.readline().strip() != b"ply":
            raise ValueError("No es un PLY")
        formato, elementos, actual = None, [], None
        while True:
            linea = fh.readline().decode("ascii", "ignore").strip()
            p = linea.split()
            if not p:
                continue
            if p[0] == "format":
                formato = p[1]
            elif p[0] == "element":
                actual = {"nombre": p[1], "n": int(p[2]), "props": []}
                elementos.append(actual)
            elif p[0] == "property":
                if p[1] == "list":
                    actual["props"].append(("list", p[4], p[2], p[3]))
                else:
                    actual["props"].append(("esc", p[2], p[1]))
            elif p[0] == "end_header":
                break
        datos = {}
        if formato == "ascii":
            for el in elementos:
                filas = []
                for _ in range(el["n"]):
                    vals = fh.readline().split()
                    fila, k = {}, 0
                    for pr in el["props"]:
                        if pr[0] == "esc":
                            fila[pr[1]] = float(vals[k]); k += 1
                        else:
                            cnt = int(vals[k]); k += 1
                            fila[pr[1]] = [int(x) for x in vals[k:k + cnt]]; k += cnt
                    filas.append(fila)
                datos[el["nombre"]] = filas
        else:
            end = "<" if formato == "binary_little_endian" else ">"
            for el in elementos:
                filas = []
                for _ in range(el["n"]):
                    fila = {}
                    for pr in el["props"]:
                        if pr[0] == "esc":
                            t = _TIPOS_PLY[pr[2]]
                            fila[pr[1]] = struct.unpack(end + t, fh.read(struct.calcsize(t)))[0]
                        else:
                            tc, ti = _TIPOS_PLY[pr[2]], _TIPOS_PLY[pr[3]]
                            cnt = struct.unpack(end + tc, fh.read(struct.calcsize(tc)))[0]
                            fila[pr[1]] = list(struct.unpack(end + ti * cnt,
                                                             fh.read(struct.calcsize(ti) * cnt)))
                    filas.append(fila)
                datos[el["nombre"]] = filas
    vert = np.array([[r["x"], r["y"], r["z"]] for r in datos.get("vertex", [])], float)
    caras = []
    for r in datos.get("face", []):
        idx = r.get("vertex_indices", r.get("vertex_index"))
        for k in range(1, len(idx) - 1):
            caras.append([idx[0], idx[k], idx[k + 1]])
    return vert, (np.array(caras, int) if caras else None)


def escribir_ply(ruta, v, f):
    with open(ruta, "wb") as fh:
        cab = ("ply\nformat binary_little_endian 1.0\n"
               f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
               f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
        fh.write(cab.encode("ascii"))
        fh.write(np.asarray(v, "<f4").tobytes())
        for tri in f:
            fh.write(struct.pack("<B3i", 3, *tri))


# ---------------------------------------------------------------------------
# Preprocesamiento
# ---------------------------------------------------------------------------

def muestrear_superficie(v, f, n, rng):
    """Muestrea n puntos repartidos uniformemente sobre la superficie."""
    if f is None or len(f) == 0:
        idx = rng.choice(len(v), size=n, replace=len(v) < n)
        return v[idx]
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    tri = rng.choice(len(f), size=n, p=areas / areas.sum())
    u, w = rng.random(n), rng.random(n)
    fuera = u + w > 1
    u[fuera], w[fuera] = 1 - u[fuera], 1 - w[fuera]
    return a[tri] + u[:, None] * (b[tri] - a[tri]) + w[:, None] * (c[tri] - a[tri])


def a_marco_pca(p):
    """Centra la nube y la rota a sus ejes principales (mayor varianza primero)."""
    p = p - p.mean(axis=0)
    val, vec = np.linalg.eigh(np.cov(p.T))
    vec = vec[:, np.argsort(val)[::-1]]
    if np.linalg.det(vec) < 0:
        vec[:, 2] *= -1
    return p @ vec


def descriptor(p, rng, bins=24):
    """Resumen barato de la forma, para preseleccionar candidatas."""
    ext = np.ptp(p, axis=0)
    i, j = rng.integers(0, len(p), 4000), rng.integers(0, len(p), 4000)
    d = np.linalg.norm(p[i] - p[j], axis=1)
    hist, _ = np.histogram(d / d.max(), bins=bins, range=(0, 1), density=True)
    return np.concatenate([np.log(ext + 1e-9), hist / bins])


def preparar(ruta, rng, recorte=0.0):
    v, f = leer_malla(ruta)
    p = muestrear_superficie(v, f, N_DENSO, rng)
    if recorte > 0:
        p = recortar(p, recorte, rng)
    p = a_marco_pca(p)
    return p.astype(np.float32), descriptor(p, rng)


def recortar(p, fraccion, rng):
    """Simula un fragmento: elimina una fracción de la pieza de un lado de un plano al azar."""
    n = rng.normal(size=3); n /= np.linalg.norm(n)
    s = (p - p.mean(axis=0)) @ n
    return p[s > np.quantile(s, fraccion)]


# ---------------------------------------------------------------------------
# Comparación fina: ICP rígido + distancia de Chamfer
# ---------------------------------------------------------------------------

_GIROS_4 = [np.diag(s) for s in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1])]


def _giros_24():
    """Las 24 rotaciones que llevan ejes a ejes: además de invertir sentidos, permite que los
    ejes principales de la consulta y la referencia queden intercambiados."""
    import itertools
    giros = list(_GIROS_4)
    for perm in itertools.permutations(range(3)):
        for signos in itertools.product((1, -1), repeat=3):
            g = np.eye(3)[list(perm)] * np.array(signos)[:, None]
            if np.linalg.det(g) > 0 and not any(np.array_equal(g, h) for h in giros):
                giros.append(g)
    return giros


GIROS = {4: _GIROS_4, 24: _giros_24()}
N_ORIENTACIONES = 4      # orientaciones iniciales de la etapa rápida (4 o 24)


def _kabsch(a, b):
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(vt.T @ u.T))
    r = vt.T @ np.diag([1, 1, d]) @ u.T
    return r, cb - r @ ca


def _icp(x, ref, arbol, iters):
    for _ in range(iters):
        d, i = arbol.query(x)
        k = d <= np.partition(d, int(len(d) * RECORTE_ICP))[int(len(d) * RECORTE_ICP)]
        r, t = _kabsch(x[k], ref[i[k]])
        x = x @ r.T + t
    return x


def alinear_grueso(q, ref):
    """Etapa rápida: prueba las orientaciones iniciales (4 sentidos de los ejes PCA, o las 24
    rotaciones entre ejes) y se queda con la mejor."""
    qs, rs = q[:N_GRUESO], ref[:N_GRUESO * 4]
    arbol = cKDTree(rs)
    mejor = (np.inf, None)
    for g in GIROS[N_ORIENTACIONES]:
        x = _icp(qs @ g.T, rs, arbol, 4)
        d = arbol.query(x)[0].mean()
        if d < mejor[0]:
            mejor = (d, g)
    g = mejor[1]
    x = _icp(qs @ g.T, rs, arbol, 8)
    r, t = _kabsch(qs @ g.T, x)
    return arbol.query(x)[0].mean(), (r @ g, t)


def comparar_fino(q, ref, transf):
    """Etapa fina: refina la alineación y mide la distancia media entre superficies (mm)."""
    r0, t0 = transf
    arbol_ref = cKDTree(ref)
    x = _icp(q[:N_FINO] @ r0.T + t0, ref, arbol_ref, 20)
    r, t = _kabsch(q[:N_FINO], x)
    qa = q @ r.T + t
    d1 = arbol_ref.query(qa[:N_FINO])[0]                  # consulta -> referencia
    d2 = cKDTree(qa).query(ref[:N_FINO])[0]               # referencia -> consulta
    # si la consulta es un fragmento, no se penaliza la parte de la referencia que falta
    cubierta = min(1.0, max(0.5, len(q) / len(ref)))
    d2 = np.sort(d2)[: int(len(d2) * cubierta)]
    return 0.5 * (d1.mean() + d2.mean())


# ---------------------------------------------------------------------------
# Índice
# ---------------------------------------------------------------------------

def indexar(args):
    rng = np.random.default_rng(0)
    base = os.path.dirname(os.path.abspath(args.metadata))
    puntos, descs, etiquetas = [], [], []
    with open(args.metadata, newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    for fila in filas:
        if fila.get("aprobado", "Sí").strip().lower() in ("no", "false", "0"):
            continue
        ruta = os.path.join(base, fila["archivo_liviano"])
        p, d = preparar(ruta, rng)
        puntos.append(p); descs.append(d)
        etiquetas.append((fila["id_especie"], fila["id_individuo"], fila["region"],
                          int(fila["posicion"]), fila.get("id_escaneo", "")))
        print(f"  {fila['archivo_liviano']}", file=sys.stderr)
    descs = np.array(descs)
    np.savez_compressed(args.salida, puntos=np.array(puntos, dtype=object),
                        descs=descs, media=descs.mean(0), desv=descs.std(0) + 1e-9,
                        etiquetas=np.array(etiquetas, dtype=object))
    print(f"Índice con {len(puntos)} vértebras guardado en {args.salida}")


def cargar_indice(ruta):
    z = np.load(ruta, allow_pickle=True)
    return {"puntos": [np.asarray(x, dtype=np.float64) for x in z["puntos"]], "descs": z["descs"], "media": z["media"],
            "desv": z["desv"], "etiquetas": [tuple(e) for e in z["etiquetas"]]}


def buscar(q, dq, ind, excluir=None, top=5):
    """Devuelve las candidatas: (especie, región, posición), distancia, individuo, prob. relativa."""
    validos = [i for i, e in enumerate(ind["etiquetas"]) if excluir is None or e[1] != excluir]
    if len(validos) > MAX_SIN_PRESELECCION:
        z = (ind["descs"][validos] - ind["media"]) / ind["desv"]
        zq = (dq - ind["media"]) / ind["desv"]
        validos = [validos[o] for o in np.argsort(np.linalg.norm(z - zq, axis=1))[:N_PRESELECCION]]
    gruesos = sorted((alinear_grueso(q, ind["puntos"][i]) + (i,) for i in validos), key=lambda x: x[0])
    por_etiqueta = {}
    for _, transf, i in gruesos[:N_FINALISTAS]:
        dist = comparar_fino(q, ind["puntos"][i], transf)
        e = ind["etiquetas"][i]
        clave = (e[0], e[2], e[3])                      # especie, región, posición
        if dist < por_etiqueta.get(clave, (np.inf,))[0]:
            por_etiqueta[clave] = (dist, e[1])
    res = sorted(((k, v[0], v[1]) for k, v in por_etiqueta.items()), key=lambda x: x[1])
    d = np.array([r[1] for r in res])
    pesos = np.exp(-((d / d[0]) ** 2 - 1) * 6)
    prob = pesos / pesos.sum()
    return [(r[0], r[1], r[2], p) for r, p in zip(res, prob)][:top]


def codigo(region, pos):
    pref = {"cervical": "C", "torácica": "T", "toracica": "T", "caudal": "Ca",
            "notario": "N"}.get(region.lower(), region[:3].upper())
    return f"{pref}{pos:02d}"


def identificar(args):
    global N_ORIENTACIONES
    N_ORIENTACIONES = args.orientaciones
    rng = np.random.default_rng(1)
    ind = cargar_indice(args.indice)
    q, dq = preparar(args.modelo, rng)
    q = q.astype(np.float64)
    res = buscar(q, dq, ind, top=args.top)
    print(f"\nCandidatas para {os.path.basename(args.modelo)}:\n")
    print(f"  {'Especie':<10}{'Posición':<10}{'Prob. rel.':>11}{'Dist. (mm)':>12}  Individuo más parecido")
    for (esp, reg, pos), dist, indiv, p in res:
        print(f"  {esp:<10}{codigo(reg, pos):<10}{p:>10.0%}{dist:>12.3f}  {indiv}")
    if args.umbral and res[0][1] > args.umbral:
        print(f"\n  Atención: la mejor distancia ({res[0][1]:.3f} mm) supera el umbral "
              f"({args.umbral} mm). Puede no haber nada parecido en la base.")
    print("\n  La probabilidad es relativa entre candidatas, todavía no está calibrada.")


def evaluar(args):
    """Deja afuera un individuo entero por vez y trata de ubicar sus vértebras con el resto."""
    global N_ORIENTACIONES
    N_ORIENTACIONES = args.orientaciones
    rng = np.random.default_rng(2)
    ind = cargar_indice(args.indice)
    total = esp_ok = exacta = mas_menos1 = top3 = 0
    dist_aciertos = []
    errores = defaultdict(int)
    t0 = time.time()
    consultas = list(range(len(ind["etiquetas"])))
    if args.muestra and args.muestra < len(consultas):
        consultas = sorted(rng.choice(consultas, args.muestra, replace=False))
    for i in consultas:
        e = ind["etiquetas"][i]
        q = ind["puntos"][i]
        if args.recorte > 0:
            q = a_marco_pca(recortar(q, args.recorte, rng)).astype(np.float32)
        dq = descriptor(q, rng)
        res = buscar(q, dq, ind, excluir=e[1], top=3)
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
    print(f"\nEvaluación dejando un individuo afuera ({total} vértebras, "
          f"recorte {args.recorte:.0%}, {args.orientaciones} orientaciones, {time.time() - t0:.0f} s)\n")
    print(f"  Especie correcta:            {esp_ok / total:6.1%}")
    print(f"  Posición exacta:             {exacta / total:6.1%}")
    print(f"  Posición con error ±1:       {mas_menos1 / total:6.1%}")
    print(f"  Correcta entre las 3 primeras: {top3 / total:4.1%}")
    if errores:
        print("  Errores mayores a 1 posición: " +
              ", ".join(f"{k} posiciones: {v}" for k, v in sorted(errores.items())))
    if dist_aciertos:
        print(f"\n  Umbral sugerido para 'no se parece a nada': "
              f"{np.percentile(dist_aciertos, 95) * 1.5:.3f} mm")


# ---------------------------------------------------------------------------
# Base sintética de prueba
# ---------------------------------------------------------------------------

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


def sintetico(args):
    rng = np.random.default_rng(args.semilla)
    especies = {
        "ESPAAA": {"n": 13, "tam": 12, "largo": 0.9, "espina": 0.30},
        "ESPBBB": {"n": 15, "tam": 14, "largo": 1.1, "espina": 0.25},
        "ESPCCC": {"n": 15, "tam": 15, "largo": 1.0, "espina": 0.40},  # parecida a B a propósito
    }
    os.makedirs(os.path.join(args.salida, "mallas"), exist_ok=True)
    filas = []
    for esp, sp in especies.items():
        for k in range(args.individuos):
            indiv = f"{esp}-{k + 1:03d}"
            iv = {"escala": rng.normal(1, 0.07), **{c: rng.normal(1, 0.06) for c in "abcdefg"}}
            for pos in range(1, sp["n"] + 1):
                t = (pos - 1) / (sp["n"] - 1)
                v, f = vertebra_sintetica(t, sp, iv, rng)
                nombre = f"mallas/{esp}_{indiv}_C{pos:02d}_v1.ply"
                escribir_ply(os.path.join(args.salida, nombre), v, f)
                filas.append({"id_escaneo": f"{indiv}-C{pos:02d}", "archivo_liviano": nombre,
                              "id_especie": esp, "id_individuo": indiv, "region": "Cervical",
                              "posicion": pos, "aprobado": "Sí"})
    with open(os.path.join(args.salida, "metadata.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    print(f"{len(filas)} vértebras sintéticas en {args.salida}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sintetico", help="generar base de prueba")
    s.add_argument("--salida", default="base_sintetica")
    s.add_argument("--individuos", type=int, default=4)
    s.add_argument("--semilla", type=int, default=42)
    s.set_defaults(func=sintetico)

    s = sub.add_parser("indexar", help="procesar la base")
    s.add_argument("--metadata", required=True)
    s.add_argument("--salida", default="indice.npz")
    s.set_defaults(func=indexar)

    s = sub.add_parser("identificar", help="identificar una vértebra")
    s.add_argument("modelo")
    s.add_argument("--indice", default="indice.npz")
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--umbral", type=float, default=None, help="distancia en mm (sale de 'evaluar')")
    s.add_argument("--orientaciones", type=int, choices=(4, 24), default=N_ORIENTACIONES,
                   help="orientaciones iniciales de la alineación rápida")
    s.set_defaults(func=identificar)

    s = sub.add_parser("evaluar", help="medir precisión dejando un individuo afuera")
    s.add_argument("--indice", default="indice.npz")
    s.add_argument("--recorte", type=float, default=0.0,
                   help="fracción a eliminar de cada consulta para simular fragmentos (ej. 0.3)")
    s.add_argument("--muestra", type=int, default=0,
                   help="evaluar solo N vértebras al azar (más rápido)")
    s.add_argument("--orientaciones", type=int, choices=(4, 24), default=N_ORIENTACIONES,
                   help="orientaciones iniciales de la alineación rápida")
    s.set_defaults(func=evaluar)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
