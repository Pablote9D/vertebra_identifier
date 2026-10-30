"""De malla a nube de puntos comparable: muestreo, marco PCA, normales, recorte, descriptor."""

import numpy as np

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
    """Resumen barato de la forma, para preseleccionar candidatas."""
    ext = np.ptp(p, axis=0)
    i, j = rng.integers(0, len(p), 4000), rng.integers(0, len(p), 4000)
    d = np.linalg.norm(p[i] - p[j], axis=1)
    hist, _ = np.histogram(d / d.max(), bins=bins, range=(0, 1), density=True)
    return np.concatenate([np.log(ext + 1e-9), hist / bins])


def preparar(ruta, rng, recorte=0.0, normales=False):
    """Nube de puntos en el marco PCA y su descriptor. Con normales=True devuelve también
    las normales en ese marco (las necesita el ICP punto a plano en las referencias)."""
    v, f = leer_malla(ruta)
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
