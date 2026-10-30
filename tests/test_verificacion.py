import csv

import numpy as np
import pytest
import trimesh

from vertebras.cli import main
from vertebras.mallas import escribir_ply
from vertebras.verificacion import verificar

COLUMNAS = ["id_escaneo", "archivo_liviano", "id_especie", "id_individuo", "region", "posicion", "aprobado"]


def _malla(carpeta, nombre, escala=1.0, basura=False):
    """Una pieza continua de ~16 mm (las vértebras sintéticas son primitivas superpuestas)."""
    m = trimesh.creation.icosphere(subdivisions=4, radius=8.0)
    v, f = np.asarray(m.vertices) * [1.0, 0.7, 0.5], np.asarray(m.faces)
    if basura:
        b = trimesh.creation.icosphere(subdivisions=2, radius=3.0)
        f = np.vstack([f, np.asarray(b.faces) + len(v)])
        v = np.vstack([v, np.asarray(b.vertices) + 40])
    (carpeta / "m").mkdir(exist_ok=True)
    escribir_ply(str(carpeta / "m" / nombre), v * escala, f)
    return f"m/{nombre}"


def _planilla(carpeta, filas, columnas=COLUMNAS):
    ruta = carpeta / "metadata.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(columnas); w.writerows(filas)
    return str(ruta)


def _niveles(r):
    return {(p["nivel"], p["id"]): p["mensaje"] for p in r["problemas"]}


def test_errores_de_planilla(tmp_path):
    a = _malla(tmp_path, "a.ply")
    ruta = _planilla(tmp_path, [
        ["A1", a, "ESP", "I1", "Cervical", 1, "Sí"],
        ["A2", a, "ESP", "I1", "Lumbar", 2, "Sí"],           # región inválida
        ["A3", "m/no.ply", "ESP", "I1", "Cervical", 3, "Sí"],  # archivo que falta
        ["A4", a, "OTRA", "I1", "Cervical", 4, "Sí"],         # mismo individuo, otra especie
        ["A1", a, "ESP", "I2", "Cervical", 1, "quizás"],      # id repetido, aprobado raro
        ["A6", a, "ESP", "I2", "Cervical", "x", "No"],        # no aprobada: no se revisa
    ])
    r = verificar(ruta)
    errores = [p for p in r["problemas"] if p["nivel"] == "error"]
    assert {p["fila"] for p in errores} == {3, 4, 5}
    assert any("Lumbar" in p["mensaje"] for p in errores)
    assert any("No existe" in p["mensaje"] for p in errores)
    assert any("dos especies" in p["mensaje"] for p in errores)
    avisos = " ".join(p["mensaje"] for p in r["problemas"] if p["nivel"] == "aviso")
    assert "repetido" in avisos and "aprobado" in avisos
    assert r["resumen"]["aprobadas"] == 2


def test_faltan_columnas(tmp_path):
    ruta = _planilla(tmp_path, [["A1", "m/a.ply"]], columnas=["id_escaneo", "archivo_liviano"])
    r = verificar(ruta)
    assert r["problemas"][0]["nivel"] == "error" and "Faltan columnas" in r["problemas"][0]["mensaje"]


def test_individuo_en_otra_unidad(tmp_path):
    filas = []
    for indiv, escala in (("I1", 1.0), ("I2", 1.05), ("I3", 0.1)):     # I3 exportado en cm
        for pos in (1, 2, 3):
            filas.append([f"{indiv}-{pos}", _malla(tmp_path, f"{indiv}_{pos}.ply", escala),
                          "ESP", indiv, "Cervical", pos, "Sí"])
    r = verificar(_planilla(tmp_path, filas))
    avisos = [p for p in r["problemas"] if p["nivel"] == "aviso"]
    assert [p["id"] for p in avisos] == ["I3"]                  # un solo aviso, para el individuo
    assert "otra unidad" in avisos[0]["mensaje"] and "dos individuos" not in avisos[0]["mensaje"]


def test_piezas_sueltas_y_posiciones_faltantes(tmp_path):
    filas = [["I1-1", _malla(tmp_path, "s.ply", basura=True), "ESP", "I1", "Cervical", 1, "Sí"],
             ["I1-3", _malla(tmp_path, "b.ply"), "ESP", "I1", "Cervical", 3, "Sí"]]
    r = verificar(_planilla(tmp_path, filas))
    mensajes = _niveles(r)
    assert "1 pieza suelta" in mensajes[("aviso", "I1-1")]
    assert "C02" in mensajes[("info", "I1")]
    assert "un solo individuo" in mensajes[("info", "ESP")]


def test_cli_sale_con_error(tmp_path, capsys):
    ruta = _planilla(tmp_path, [["A1", "m/no.ply", "ESP", "I1", "Cervical", 1, "Sí"]])
    with pytest.raises(SystemExit) as e:
        main(["verificar", "--metadata", ruta])
    assert e.value.code == 1
    assert "No existe" in capsys.readouterr().out
