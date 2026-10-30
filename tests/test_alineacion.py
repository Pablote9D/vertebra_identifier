import numpy as np
import pytest

from vertebras import config as cfg
from vertebras.alineacion import (GIROS, alinear_fino, alinear_grueso, distancia_superficies,
                                  kabsch)
from vertebras.preproceso import ejes_pca, muestrear_superficie, recortar


def test_24_rotaciones():
    g = GIROS[24]
    assert len(g) == 24
    assert len({x.tobytes() for x in g}) == 24
    assert all(np.allclose(x @ x.T, np.eye(3)) and np.linalg.det(x) == pytest.approx(1) for x in g)
    assert all(any(np.array_equal(a, b) for b in g) for a in GIROS[4])


def test_kabsch_recupera_la_transformacion():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(100, 3))
    r, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    r *= np.sign(np.linalg.det(r))
    t = np.array([1.0, -2.0, 0.5])
    r2, t2 = kabsch(a, a @ r.T + t)
    assert np.allclose(r2, r) and np.allclose(t2, t)


def _dos_muestreos(v, f, recorte=0.0):
    """Referencia y consulta: dos muestreos de la misma malla, cada uno en su marco PCA,
    y la transformación verdadera de la consulta a la referencia."""
    pa, na = muestrear_superficie(v, f, 8000, np.random.default_rng(1), normales=True)
    rb = np.random.default_rng(2)
    pb = muestrear_superficie(v, f, 8000, rb)
    if recorte:
        pb = recortar(pb, recorte, rb)
    ca, va = ejes_pca(pa)
    cb, vb = ejes_pca(pb)
    return (pa - ca) @ va, na @ va, (pb - cb) @ vb, va.T @ vb, (cb - ca) @ va


@pytest.mark.parametrize("motor, icp", [("scipy", "punto"), ("open3d", "punto"), ("open3d", "plano")])
@pytest.mark.parametrize("orientaciones", [4, 24])
def test_alinea_la_misma_pieza(vertebra, motor, icp, orientaciones):
    cfg.configurar(motor, icp, orientaciones)
    ref, normales, q, r_ok, t_ok = _dos_muestreos(*vertebra)
    _, transf = alinear_grueso(q, ref, normales, {})
    r, t = alinear_fino(q, ref, transf, normales, {})
    # la pieza es simétrica, así que se compara contra la distancia con la transformación verdadera
    assert distancia_superficies(q, ref, r, t) < distancia_superficies(q, ref, r_ok, t_ok) + 0.01


def test_punto_a_plano_alinea_un_fragmento(vertebra):
    cfg.configurar("open3d", "plano", 24)
    ref, normales, q, r_ok, t_ok = _dos_muestreos(*vertebra, recorte=0.3)
    _, transf = alinear_grueso(q, ref, normales, {})
    r, t = alinear_fino(q, ref, transf, normales, {})
    assert distancia_superficies(q, ref, r, t) < distancia_superficies(q, ref, r_ok, t_ok) + 0.01


def test_fragmento_no_penaliza_lo_que_falta(vertebra):
    """Una mitad de la pieza, muestreada con tantos puntos como la entera (como un archivo real)."""
    v, f = vertebra
    ref = muestrear_superficie(v, f, 8000, np.random.default_rng(1))
    q = muestrear_superficie(v, f, 16000, np.random.default_rng(2))
    q = q[q[:, 0] > np.median(q[:, 0])][:8000]
    r, t = np.eye(3), np.zeros(3)
    con = distancia_superficies(q, ref, r, t, fragmento=True)
    sin = distancia_superficies(q, ref, r, t)
    assert con < 0.5 * sin
    # una pieza entera da lo mismo se marque o no como fragmento (cubre toda la referencia)
    entera = muestrear_superficie(v, f, 8000, np.random.default_rng(3))
    assert distancia_superficies(entera, ref, r, t, fragmento=True) == pytest.approx(
        distancia_superficies(entera, ref, r, t), rel=0.02)
