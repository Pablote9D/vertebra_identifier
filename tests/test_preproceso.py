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


def test_limpiar_quita_piezas_sueltas():
    import trimesh
    from vertebras.preproceso import limpiar_piezas
    esfera = trimesh.creation.icosphere(subdivisions=3, radius=8.0)
    v, f = np.asarray(esfera.vertices), np.asarray(esfera.faces)
    cv, cf = _caja((100, 0, 0), (2, 2, 2))               # basura lejos de la vértebra
    v2, f2 = np.vstack([v, cv]), np.vstack([f, cf + len(v)])
    vl, fl, quitada, piezas = limpiar_piezas(v2, f2)
    assert piezas == 1 and len(fl) == len(f)
    assert np.allclose(np.sort(vl[fl].reshape(-1, 3), axis=0), np.sort(v[f].reshape(-1, 3), axis=0))
    assert 0 < quitada < 0.1


def test_limpiar_no_toca_una_malla_de_una_pieza():
    from vertebras.preproceso import limpiar_piezas
    from vertebras.sintetico import _caja as caja
    v, f = caja((0, 0, 0), (2, 3, 4))
    vl, fl, quitada, piezas = limpiar_piezas(v.astype(float), f)
    assert vl is not None and np.array_equal(fl, f) and quitada == 0 and piezas == 0


def test_limpiar_vertices_repetidos_no_parten_la_malla():
    """Open3D duplica vértices en las costuras de textura de los OBJ; no son piezas distintas."""
    from vertebras.preproceso import limpiar_piezas
    v, f = _caja((0, 0, 0), (2, 3, 4))
    v = v.astype(float)
    f = f.copy()
    v = np.vstack([v, v])                                 # la mitad de las caras usa los duplicados
    f[6:] += 8
    _, fl, quitada, piezas = limpiar_piezas(v, f)
    assert piezas == 0 and quitada == 0 and len(fl) == len(f)


def test_limpiar_conserva_parches_pegados():
    from vertebras.preproceso import limpiar_piezas
    v, f = _caja((0, 0, 0), (10, 10, 10))
    v = v.astype(float)
    pv, pf = _caja((5.1, 0, 0), (0.1, 3, 3))              # parche a 0.1 mm de la superficie
    v2, f2 = np.vstack([v, pv]), np.vstack([f, pf + len(v)])
    _, fl, quitada, piezas = limpiar_piezas(v2, f2)
    assert piezas == 0 and len(fl) == len(f2)
