import numpy as np
import pytest

from vertebras.mallas import escribir_ply, leer_malla


def _triangulos(v, f):
    """Triángulos como conjunto de coordenadas, independiente del orden de los vértices."""
    t = np.round(v[f], 4)
    t = np.sort(t.reshape(len(f), -1).view([("", t.dtype)] * 9), axis=0)
    return t


def test_ply_ida_y_vuelta(tmp_path, vertebra):
    v, f = vertebra
    ruta = str(tmp_path / "v.ply")
    escribir_ply(ruta, v, f)
    v2, f2 = leer_malla(ruta)
    assert np.allclose(v2, v.astype(np.float32), atol=1e-5)
    assert np.array_equal(f2, f)


@pytest.mark.parametrize("ext", [".obj", ".stl", ".off"])
def test_otros_formatos(tmp_path, vertebra, ext):
    import trimesh
    v, f = vertebra
    ruta = str(tmp_path / f"v{ext}")
    trimesh.Trimesh(v, f, process=False).export(ruta)
    v2, f2 = leer_malla(ruta)
    assert len(f2) == len(f)
    assert np.allclose(np.sort(v2[f2].reshape(-1, 3), axis=0),
                       np.sort(v[f].reshape(-1, 3), axis=0), atol=1e-4)


def test_archivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        leer_malla(str(tmp_path / "no_existe.ply"))
