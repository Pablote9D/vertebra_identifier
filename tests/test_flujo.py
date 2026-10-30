"""Flujo completo sobre una base sintética chica: indexar, identificar y evaluar."""

import numpy as np
import pytest

from vertebras import cli
from vertebras import config as cfg
from vertebras.evaluacion import evaluar
from vertebras.indice import buscar, cargar_indice, identificar, indexar, leer_metadata


def test_indice(base_chica):
    ind = cargar_indice(base_chica["indice"])
    assert len(ind["puntos"]) == 86
    assert all(len(n) == len(p) for p, n in zip(ind["puntos"], ind["normales"]))
    assert ind["etiquetas"][0][:4] == ("ESPAAA", "ESPAAA-001", "Cervical", 1)


def test_identifica_una_pieza_de_la_base(base_chica):
    ind = cargar_indice(base_chica["indice"])
    malla = base_chica["carpeta"] / "mallas" / "ESPBBB_ESPBBB-002_C08_v1.ply"
    (esp, reg, pos), dist, indiv, prob = identificar(str(malla), ind, top=3)[0]
    assert (esp, reg, pos, indiv) == ("ESPBBB", "Cervical", 8, "ESPBBB-002")
    assert dist < 0.3            # el índice de prueba tiene menos puntos, por eso la distancia es mayor


def test_evaluar_da_lo_mismo_en_paralelo(base_chica):
    cfg.configurar("open3d", "plano", 4)
    a = evaluar(base_chica["indice"], recorte=0.3, muestra=4, nucleos=1)
    b = evaluar(base_chica["indice"], recorte=0.3, muestra=4, nucleos=2)
    assert a["total"] == b["total"] == 4
    # mismas candidatas; las distancias pueden diferir en el último decimal por el orden de las sumas
    for da, db in zip(a["detalle"], b["detalle"]):
        assert [c[0] for c in da["candidatas"]] == [c[0] for c in db["candidatas"]]
        assert [c[1] for c in da["candidatas"]] == pytest.approx([c[1] for c in db["candidatas"]], rel=1e-9)
    for k in ("especie", "exacta", "mas_menos1", "top3"):
        assert a[k] == b[k]


def test_indice_viejo_sin_normales(base_chica, tmp_path):
    z = dict(np.load(base_chica["indice"], allow_pickle=True))
    del z["normales"]
    viejo = str(tmp_path / "viejo.npz")
    np.savez_compressed(viejo, **z)
    ind = cargar_indice(viejo)
    assert ind["normales"][0] is None
    q = ind["puntos"][5]
    res = buscar(q, None, ind, top=3)            # la consulta coincide exactamente con la referencia 5
    assert res[0][0] == ind["etiquetas"][5][0:1] + ind["etiquetas"][5][2:4]
    assert res[0][1] == pytest.approx(0, abs=1e-6)
    assert np.isfinite([r[3] for r in res]).all()


def _metadata(tmp_path, filas):
    ruta = tmp_path / "metadata.csv"
    ruta.write_text("id_escaneo,archivo_liviano,id_especie,id_individuo,region,posicion,aprobado\n"
                    + "\n".join(filas) + "\n", encoding="utf-8")
    return str(ruta)


def test_metadata_ignora_no_aprobadas_y_valida_regiones(tmp_path):
    ruta = _metadata(tmp_path, ["a,m/a.ply,ESP,I1,Cervical,1,Sí",
                                "b,m/b.ply,ESP,I1,Pigóstilo,1,Sí",
                                "c,m/c.ply,ESP,I1,Lumbar,1,No"])
    filas = leer_metadata(ruta)
    assert [f["id_escaneo"] for f in filas] == ["a", "b"]
    assert filas[0]["ruta"] == str(tmp_path / "m" / "a.ply")
    ruta = _metadata(tmp_path, ["a,m/a.ply,ESP,I1,Cervical,1,Sí", "b,m/b.ply,ESP,I1,Lumbar,2,Sí"])
    with pytest.raises(ValueError, match="fila 3.*Lumbar"):
        leer_metadata(ruta)
    with pytest.raises(ValueError):
        indexar(ruta, str(tmp_path / "i.npz"))


def test_cli_identificar(base_chica, capsys):
    malla = base_chica["carpeta"] / "mallas" / "ESPAAA_ESPAAA-001_C03_v1.ply"
    cli.main(["identificar", str(malla), "--indice", base_chica["indice"], "--top", "2",
              "--orientaciones", "4"])
    salida = capsys.readouterr().out
    assert "ESPAAA    C03" in salida
