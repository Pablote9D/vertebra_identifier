import os

import numpy as np
import pytest

from vertebras import config as cfg
from vertebras.sintetico import generar_base, vertebra_sintetica

_PARAMETROS = ("N_DENSO", "MOTOR", "ICP", "N_ORIENTACIONES", "MAX_SIN_PRESELECCION", "N_PRESELECCION")


@pytest.fixture(autouse=True)
def restaurar_config():
    """Cada test puede cambiar la configuración; se restaura al terminar."""
    antes = {k: getattr(cfg, k) for k in _PARAMETROS}
    yield
    for k, v in antes.items():
        setattr(cfg, k, v)


@pytest.fixture
def vertebra():
    """Una vértebra sintética (vértices, caras) en posición y orientación arbitrarias."""
    sp = {"n": 13, "tam": 12, "largo": 0.9, "espina": 0.30}
    iv = {"escala": 1.0, **{c: 1.0 for c in "abcdefg"}}
    return vertebra_sintetica(0.4, sp, iv, np.random.default_rng(3))


@pytest.fixture(scope="session")
def base_chica(tmp_path_factory):
    """Base sintética con 2 individuos por especie (86 vértebras) y su índice."""
    from vertebras.indice import indexar
    carpeta = tmp_path_factory.mktemp("base")
    generar_base(str(carpeta), individuos=2, semilla=11)
    indice = str(carpeta / "indice.npz")
    n_denso = cfg.N_DENSO
    cfg.N_DENSO = 5000                       # índice más liviano para que los tests sean rápidos
    try:
        indexar(str(carpeta / "metadata.csv"), indice)
    finally:
        cfg.N_DENSO = n_denso
    return {"carpeta": carpeta, "metadata": str(carpeta / "metadata.csv"), "indice": indice,
            "mallas": sorted(os.listdir(carpeta / "mallas"))}
