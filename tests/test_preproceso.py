import numpy as np
import pytest

from vertebras.preproceso import a_marco_pca, ejes_pca, muestrear_superficie, recortar
from vertebras.sintetico import _caja


def test_muestreo_sobre_la_superficie_con_normales():
    v, f = _caja((0, 0, 0), (2, 4, 6))
    p, n = muestrear_superficie(v.astype(float), f, 3000, np.random.default_rng(0), normales=True)
    mitad = np.array([1, 2, 3])
    # cada punto está sobre alguna cara de la caja, y su normal es perpendicular a esa cara
    en_cara = np.isclose(np.abs(p), mitad, atol=1e-9)
    assert en_cara.any(axis=1).all()
    assert np.allclose(np.linalg.norm(n, axis=1), 1)
    assert np.allclose(np.abs(n)[en_cara.any(axis=1)].max(axis=1), 1)


def test_muestreo_proporcional_al_area():
    v, f = _caja((0, 0, 0), (1, 1, 10))          # las caras largas tienen 10 veces más área
    p = muestrear_superficie(v.astype(float), f, 20000, np.random.default_rng(0))
    en_tapas = np.isclose(np.abs(p[:, 2]), 5).mean()
    assert en_tapas == pytest.approx(2 / 42, abs=0.01)


def test_marco_pca(vertebra):
    v, f = vertebra
    p = a_marco_pca(muestrear_superficie(v, f, 5000, np.random.default_rng(0)))
    cov = np.cov(p.T)
    assert np.allclose(p.mean(axis=0), 0, atol=1e-9)
    assert np.allclose(cov, np.diag(np.diag(cov)), atol=1e-8)
    assert cov[0, 0] >= cov[1, 1] >= cov[2, 2]
    _, vec = ejes_pca(p)
    assert np.linalg.det(vec) == pytest.approx(1)


def test_marco_pca_no_depende_de_la_posicion_inicial(vertebra):
    """Girar y mover la pieza solo puede cambiar el sentido de los ejes PCA."""
    v, f = vertebra
    p = muestrear_superficie(v, f, 5000, np.random.default_rng(0))
    q, _ = np.linalg.qr(np.random.default_rng(1).normal(size=(3, 3)))
    a, b = a_marco_pca(p), a_marco_pca(p @ q.T + 7)
    assert np.allclose(np.abs(a), np.abs(b), atol=1e-6)


def test_recortar(vertebra):
    v, f = vertebra
    p = muestrear_superficie(v, f, 10000, np.random.default_rng(0))
    assert len(recortar(p, 0.3, np.random.default_rng(0))) == pytest.approx(7000, abs=2)
