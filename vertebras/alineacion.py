"""Alineación rígida (ICP) y distancia entre superficies.

Dos etapas: una rápida, que prueba varias orientaciones iniciales con pocos puntos, y una fina
con más puntos. Dos motores: "open3d" (ICP de Open3D, punto a punto o punto a plano) y "scipy"
(el ICP original, punto a punto con recorte de pares)."""

import itertools

import numpy as np
from scipy.spatial import cKDTree

from . import config as cfg
from .mallas import o3d
from .preproceso import estimar_normales, nube_o3d

GIROS_4 = [np.diag(s) for s in ([1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1])]


def _giros_24():
    """Las 24 rotaciones que llevan ejes a ejes: además de invertir sentidos, permite que los
    ejes principales de la consulta y la referencia queden intercambiados."""
    giros = list(GIROS_4)
    for perm in itertools.permutations(range(3)):
        for signos in itertools.product((1, -1), repeat=3):
            g = np.eye(3)[list(perm)] * np.array(signos)[:, None]
            if np.linalg.det(g) > 0 and not any(np.array_equal(g, h) for h in giros):
                giros.append(g)
    return giros


GIROS = {4: GIROS_4, 24: _giros_24()}


# ---------------------------------------------------------------------------
# Motor scipy (original)
# ---------------------------------------------------------------------------

def kabsch(a, b):
    """Rotación y traslación que mejor llevan los puntos a sobre b (mínimos cuadrados)."""
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _, vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(vt.T @ u.T))
    r = vt.T @ np.diag([1, 1, d]) @ u.T
    return r, cb - r @ ca


def _icp(x, ref, arbol, iters):
    for _ in range(iters):
        d, i = arbol.query(x)
        k = d <= np.partition(d, int(len(d) * cfg.RECORTE_ICP))[int(len(d) * cfg.RECORTE_ICP)]
        r, t = kabsch(x[k], ref[i[k]])
        x = x @ r.T + t
    return x


def alinear_grueso_scipy(q, ref):
    """Etapa rápida: prueba las orientaciones iniciales (4 sentidos de los ejes PCA, o las 24
    rotaciones entre ejes) y se queda con la mejor."""
    qs, rs = q[:cfg.N_GRUESO], ref[:cfg.N_GRUESO * 4]
    arbol = cKDTree(rs)
    mejor = (np.inf, None)
    for g in GIROS[cfg.N_ORIENTACIONES]:
        x = _icp(qs @ g.T, rs, arbol, 4)
        d = arbol.query(x)[0].mean()
        if d < mejor[0]:
            mejor = (d, g)
    g = mejor[1]
    x = _icp(qs @ g.T, rs, arbol, 8)
    r, t = kabsch(qs @ g.T, x)
    return arbol.query(x)[0].mean(), (r @ g, t)


def alinear_fino_scipy(q, ref, transf):
    """Refina la alineación con ICP (20 pasos, N_FINO puntos de la consulta)."""
    r0, t0 = transf
    x = _icp(q[:cfg.N_FINO] @ r0.T + t0, ref, cKDTree(ref), 20)
    return kabsch(q[:cfg.N_FINO], x)


# ---------------------------------------------------------------------------
# Motor Open3D: mismas etapas, con el ICP de Open3D (punto a punto o punto a plano)
# ---------------------------------------------------------------------------

def _homogenea(r, t):
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = r, t
    return m


def _icp_o3d(fuente, destino, inicial, umbral, iters):
    reg = o3d().pipelines.registration
    est = (reg.TransformationEstimationPointToPlane() if cfg.ICP == "plano"
           else reg.TransformationEstimationPointToPoint())
    crit = reg.ICPConvergenceCriteria(relative_fitness=1e-7, relative_rmse=1e-7, max_iteration=iters)
    return reg.registration_icp(fuente, destino, umbral, inicial, est, crit).transformation


def _ref_o3d(ref, normales, cache):
    """Nubes Open3D de una referencia (gruesa y completa), su árbol y su escala. Se guardan
    en `cache` para no reconstruirlas en cada consulta."""
    if cache is not None and "nube" in cache:
        return cache
    if normales is None:
        normales = estimar_normales(ref)
    rs = ref[:cfg.N_GRUESO * 4]
    c = {"nube": nube_o3d(ref, normales), "gruesa": nube_o3d(rs, normales[:cfg.N_GRUESO * 4]),
         "arbol_grueso": cKDTree(rs), "escala": float(np.sqrt((ref ** 2).sum(axis=1).mean()))}
    if cache is not None:
        cache.update(c)
    return c


def alinear_grueso_o3d(q, ref, normales=None, cache=None):
    """Como alinear_grueso_scipy, con el ICP de Open3D."""
    c = _ref_o3d(ref, normales, cache)
    qs = q[:cfg.N_GRUESO]
    fuente, arbol = nube_o3d(qs), c["arbol_grueso"]
    umbral = cfg.UMBRAL_GRUESO * c["escala"]
    mejor = (np.inf, None)
    for g in GIROS[cfg.N_ORIENTACIONES]:
        m = _icp_o3d(fuente, c["gruesa"], _homogenea(g, np.zeros(3)), umbral, 4)
        d = arbol.query(qs @ m[:3, :3].T + m[:3, 3])[0].mean()
        if d < mejor[0]:
            mejor = (d, m)
    m = _icp_o3d(fuente, c["gruesa"], mejor[1], umbral, 8)
    r, t = m[:3, :3], m[:3, 3]
    return arbol.query(qs @ r.T + t)[0].mean(), (r, t)


def alinear_fino_o3d(q, ref, transf, normales=None, cache=None):
    """Como alinear_fino_scipy, con el ICP de Open3D."""
    c = _ref_o3d(ref, normales, cache)
    m = _icp_o3d(nube_o3d(q[:cfg.N_FINO]), c["nube"], _homogenea(*transf),
                 cfg.UMBRAL_FINO * c["escala"], 20)
    return m[:3, :3], m[:3, 3]


# ---------------------------------------------------------------------------
# Interfaz común
# ---------------------------------------------------------------------------

def alinear_grueso(q, ref, normales=None, cache=None):
    """Etapa rápida con el motor configurado. Devuelve (distancia aproximada, (r, t))."""
    if cfg.MOTOR == "open3d":
        return alinear_grueso_o3d(q, ref, normales, cache)
    return alinear_grueso_scipy(q, ref)


def alinear_fino(q, ref, transf, normales=None, cache=None):
    """Etapa fina con el motor configurado. Devuelve (r, t)."""
    if cfg.MOTOR == "open3d":
        return alinear_fino_o3d(q, ref, transf, normales, cache)
    return alinear_fino_scipy(q, ref, transf)


def distancia_superficies(q, ref, r, t):
    """Distancia media simétrica (mm) entre la consulta transformada y la referencia."""
    arbol_ref = cKDTree(ref)
    qa = q @ r.T + t
    d1 = arbol_ref.query(qa[:cfg.N_FINO])[0]              # consulta -> referencia
    d2 = cKDTree(qa).query(ref[:cfg.N_FINO])[0]           # referencia -> consulta
    # si la consulta es un fragmento, no se penaliza la parte de la referencia que falta
    cubierta = min(1.0, max(0.5, len(q) / len(ref)))
    d2 = np.sort(d2)[: int(len(d2) * cubierta)]
    return 0.5 * (d1.mean() + d2.mean())


def comparar_fino(q, ref, transf, normales=None, cache=None):
    """Etapa fina: refina la alineación y mide la distancia media entre superficies (mm)."""
    r, t = alinear_fino(q, ref, transf, normales, cache)
    return distancia_superficies(q, ref, r, t)
