"""De malla a nube de puntos comparable: muestreo, marco PCA, normales, recorte, descriptor."""

import numpy as np
from scipy.spatial import cKDTree

from . import config as cfg
from .mallas import leer_malla, o3d


def muestrear_superficie(v, f, n, rng, normales=False):
    """Muestrea n puntos repartidos uniformemente sobre la superficie.
    Con normales=True devuelve además la normal (unitaria) del triángulo de cada punto,
    o None si la malla no tiene caras."""
    if f is None or len(f) == 0:
        idx = rng.choice(len(v), size=n, replace=len(v) < n)
        return (v[idx], None) if normales else v[idx]
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    cruz = np.cross(b - a, c - a)
    areas = 0.5 * np.linalg.norm(cruz, axis=1)
    tri = rng.choice(len(f), size=n, p=areas / areas.sum())
    u, w = rng.random(n), rng.random(n)
    fuera = u + w > 1
    u[fuera], w[fuera] = 1 - u[fuera], 1 - w[fuera]
    p = a[tri] + u[:, None] * (b[tri] - a[tri]) + w[:, None] * (c[tri] - a[tri])
    if not normales:
        return p
    return p, cruz[tri] / (2 * areas[tri, None])


def ejes_pca(p):
    """Centro y ejes principales (columnas, mayor varianza primero, rotación propia)."""
    centro = p.mean(axis=0)
    val, vec = np.linalg.eigh(np.cov((p - centro).T))
    vec = vec[:, np.argsort(val)[::-1]]
    if np.linalg.det(vec) < 0:
        vec[:, 2] *= -1
    return centro, vec


def a_marco_pca(p):
    """Centra la nube y la rota a sus ejes principales (mayor varianza primero)."""
    centro, vec = ejes_pca(p)
    return (p - centro) @ vec


def nube_o3d(p, n=None):
    """PointCloud de Open3D a partir de puntos (y normales)."""
    m = o3d()
    nube = m.geometry.PointCloud(m.utility.Vector3dVector(np.asarray(p, dtype=np.float64)))
    if n is not None:
        nube.normals = m.utility.Vector3dVector(np.asarray(n, dtype=np.float64))
    return nube


def estimar_normales(p, k=30):
    """Normales por vecinos cercanos, para nubes sin caras."""
    nube = nube_o3d(p)
    nube.estimate_normals(o3d().geometry.KDTreeSearchParamKNN(k))
    return np.asarray(nube.normals)


def descriptor(p, rng, bins=24):
    """Descriptor original (extensiones + histograma de distancias normalizado). Ya no se usa
    para preseleccionar (ver descriptor_tamano); se sigue calculando porque consume números
    aleatorios y quitarlo cambiaría el muestreo de los índices."""
    ext = np.ptp(p, axis=0)
    i, j = rng.integers(0, len(p), 4000), rng.integers(0, len(p), 4000)
    d = np.linalg.norm(p[i] - p[j], axis=1)
    hist, _ = np.histogram(d / d.max(), bins=bins, range=(0, 1), density=True)
    return np.concatenate([np.log(ext + 1e-9), hist / bins])


def limpiar_piezas(v, f, pegada_mm=None):
    """Quita piezas ajenas a la vértebra (marcadores, restos de segmentación, basura del escaneo).

    Conserva la pieza de mayor área y las piezas pegadas a ella: aquellas con el 95% de sus
    vértices a menos de `pegada_mm` de la principal (por defecto cfg.PIEZA_PEGADA_MM, o dos aristas
    típicas si la malla es más gruesa). Así se mantienen los parches de superficie de una malla
    partida y se descarta lo que sobresale o está suelto. No reordena caras: si no hay nada que
    quitar, devuelve la malla tal cual. Devuelve (v, f, fracción de área quitada, piezas quitadas).

    Pensada para escaneos, cuya superficie es una sola malla. Una pieza armada con partes
    superpuestas que no comparten vértices (como las vértebras sintéticas) perdería partes."""
    if f is None or len(f) == 0:
        return v, f, 0.0, 0
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    # vértices repetidos (por ejemplo en costuras de textura) cuentan como uno solo
    _, unico = np.unique(np.round(v, 6), axis=0, return_inverse=True)
    unico = unico.ravel()
    g = unico[f]
    aristas = np.vstack([g[:, [0, 1]], g[:, [1, 2]], g[:, [2, 0]]])
    n_u = unico.max() + 1
    grafo = coo_matrix((np.ones(len(aristas)), (aristas[:, 0], aristas[:, 1])), shape=(n_u, n_u))
    n_piezas, etiqueta_u = connected_components(grafo, directed=False)
    etiqueta_cara = etiqueta_u[g[:, 0]]
    con_caras = np.zeros(n_piezas, bool)
    con_caras[etiqueta_cara] = True          # los vértices sin caras no cuentan como piezas
    if con_caras.sum() == 1:
        return v, f, 0.0, 0
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area_cara = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    area = np.bincount(etiqueta_cara, weights=area_cara, minlength=n_piezas)
    principal = area.argmax()
    if pegada_mm is None:
        arista = np.median(np.linalg.norm(b - a, axis=1))
        pegada_mm = max(cfg.PIEZA_PEGADA_MM, 2 * arista)
    etiqueta_v = np.full(len(v), -1)
    etiqueta_v[f.ravel()] = np.repeat(etiqueta_cara, 3)
    usados = np.where(etiqueta_v >= 0)[0]
    en_principal = usados[etiqueta_v[usados] == principal]
    d = cKDTree(v[en_principal]).query(v[usados])[0]
    # percentil 95 de la distancia a la pieza principal, por pieza
    orden = np.lexsort((d, etiqueta_v[usados]))
    lab_ord, d_ord = etiqueta_v[usados][orden], d[orden]
    inicio = np.searchsorted(lab_ord, np.arange(n_piezas))
    cuenta = np.bincount(lab_ord, minlength=n_piezas)
    p95 = d_ord[np.minimum(inicio + (0.95 * (cuenta - 1)).astype(int), len(d_ord) - 1)]
    conservar = p95 < pegada_mm
    conservar[principal] = True
    quitar = con_caras & ~conservar
    if not quitar.any():
        return v, f, 0.0, 0
    caras = f[conservar[etiqueta_cara]]
    quedan = np.unique(caras)
    nuevo = np.full(len(v), -1)
    nuevo[quedan] = np.arange(len(quedan))
    quitada = 1 - area[conservar].sum() / area.sum()
    return v[quedan], nuevo[caras], float(quitada), int(quitar.sum())


def descriptor_tamano(p):
    """Logaritmo del largo, ancho y alto de una nube en su marco PCA, para preseleccionar
    candidatas. En las pruebas con bases sintéticas grandes ubicó mejor a las referencias
    correctas que el descriptor original y que una prealineación barata."""
    return np.log(np.ptp(p, axis=0) + 1e-9)


def preparar(ruta, rng, recorte=0.0, normales=False, limpiar=False, info=None):
    """Nube de puntos en el marco PCA y su descriptor. Con normales=True devuelve también
    las normales en ese marco (las necesita el ICP punto a plano en las referencias).
    Con limpiar=True quita antes las piezas ajenas (ver limpiar_piezas) y, si se pasa un
    diccionario `info`, anota en él "area_quitada" (fracción) y "piezas_quitadas"."""
    v, f = leer_malla(ruta)
    if limpiar:
        v, f, quitada, piezas = limpiar_piezas(v, f)
        if info is not None:
            info.update(area_quitada=quitada, piezas_quitadas=piezas)
    p, n = muestrear_superficie(v, f, cfg.N_DENSO, rng, normales=True)
    if recorte > 0:
        p = recortar(p, recorte, rng)
        n = None
    centro, vec = ejes_pca(p)
    p = (p - centro) @ vec
    if not normales:
        return p.astype(np.float32), descriptor(p, rng)
    n = estimar_normales(p) if n is None else n @ vec
    return p.astype(np.float32), n.astype(np.float32), descriptor(p, rng)


def recortar(p, fraccion, rng):
    """Simula un fragmento: elimina una fracción de la pieza de un lado de un plano al azar."""
    n = rng.normal(size=3); n /= np.linalg.norm(n)
    s = (p - p.mean(axis=0)) @ n
    return p[s > np.quantile(s, fraccion)]
