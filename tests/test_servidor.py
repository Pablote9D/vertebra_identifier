"""API del servidor web, sobre la base sintética chica."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from vertebras import config as cfg  # noqa: E402
from vertebras.servidor import crear_app  # noqa: E402


@pytest.fixture(scope="module")
def cliente(base_chica, tmp_path_factory):
    especies = tmp_path_factory.mktemp("datos") / "especies.csv"
    especies.write_text("id_especie,nombre_comun,nombre_cientifico\nESPBBB,Especie B,Avis secunda\n", encoding="utf-8")
    return TestClient(crear_app(indice=base_chica["indice"], especies=str(especies), umbral_mm=0.05, max_mb=1))


def _malla(base_chica, nombre="ESPBBB_ESPBBB-002_C08_v1.ply"):
    return open(base_chica["carpeta"] / "mallas" / nombre, "rb")


def test_salud_y_coleccion(cliente):
    assert cliente.get("/api/salud").json() == {"ok": True, "vertebras": 86}
    c = cliente.get("/api/coleccion").json()
    assert c["vertebras"] == 86 and c["individuos"] == 6
    b = next(e for e in c["especies"] if e["id_especie"] == "ESPBBB")
    assert b["nombre_comun"] == "Especie B" and b["individuos"] == 2 and b["evaluable"]
    assert c["regiones"] == [{"region": "Cervical", "codigo": "C", "vertebras": 86}]


def test_identificar(cliente, base_chica):
    cfg.configurar(orientaciones=4)
    with _malla(base_chica) as fh:
        r = cliente.post("/api/identificar", files={"archivo": ("pieza.ply", fh)}, data={"fragmento": "false"})
    assert r.status_code == 200, r.text
    j = r.json()
    c = j["candidatas"][0]
    assert (c["id_especie"], c["codigo"], c["nombre_comun"]) == ("ESPBBB", "C08", "Especie B")
    assert j["supera_umbral"] is True                    # el umbral de prueba es muy bajo a propósito
    assert len(j["mapa"]["consulta"]) == len(j["mapa"]["distancias"]) > 0
    assert len(j["tamano_mm"]) == 3


def test_identificar_con_region_y_fragmento(cliente, base_chica):
    cfg.configurar(orientaciones=4)
    with _malla(base_chica) as fh:
        r = cliente.post("/api/identificar", files={"archivo": ("pieza.ply", fh)},
                         data={"fragmento": "true", "region": "Cervical"})
    assert r.status_code == 200 and r.json()["fragmento"] is True
    with _malla(base_chica) as fh:
        r = cliente.post("/api/identificar", files={"archivo": ("pieza.ply", fh)}, data={"region": "Caudal"})
    assert r.status_code == 422 and "Caudal" in r.json()["detail"]


@pytest.mark.parametrize("nombre, contenido, codigo, texto", [
    ("pieza.txt", b"hola", 422, "Formato no admitido"),
    ("pieza.ply", b"esto no es un ply", 422, "No se pudo leer"),
    ("pieza.ply", b"x" * (2 * 1024 * 1024), 413, "supera"),          # el límite de prueba es 1 MB
])
def test_errores(cliente, nombre, contenido, codigo, texto):
    r = cliente.post("/api/identificar", files={"archivo": (nombre, contenido)})
    assert r.status_code == codigo and texto in r.json()["detail"]


def test_sirve_la_pagina(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "OsteoAve" in r.text
