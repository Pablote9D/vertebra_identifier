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
    res = buscar(q, ind, top=3)            # la consulta coincide exactamente con la referencia 5
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


def test_consultas_sin_referencia_no_se_cuentan(base_chica, tmp_path):
    """Si una especie tiene un solo individuo, sus vértebras no tienen respuesta posible."""
    z = dict(np.load(base_chica["indice"], allow_pickle=True))
    quedan = [i for i, e in enumerate(z["etiquetas"]) if e[1] != "ESPAAA-002"]
    for k in ("puntos", "normales", "descs", "etiquetas"):          # descs: índice de formato anterior
        z[k] = z[k][quedan]
    ruta = str(tmp_path / "sin_par.npz")
    np.savez_compressed(ruta, **z)
    cfg.configurar("open3d", "plano", 4)
    r = evaluar(ruta, muestra=3, nucleos=1)
    assert len(r["sin_referencia"]) == 13
    assert all(e[1] == "ESPAAA-001" for e in r["sin_referencia"])
    assert all(d["consulta"][0] != "ESPAAA" for d in r["detalle"])
    assert sum(pp["n"] for pp in r["por_posicion"].values()) == r["total"] == 3


def test_resumen_por_posicion(base_chica):
    cfg.configurar("open3d", "plano", 4)
    r = evaluar(base_chica["indice"], muestra=4, nucleos=1)
    assert r["sin_referencia"] == []
    assert sum(pp["n"] for pp in r["por_posicion"].values()) == 4
    for (reg, pos), pp in r["por_posicion"].items():
        assert reg == "Cervical"
        assert sum(pp["predicciones"].values()) == pp["n"]


def test_indexar_con_limpieza_informa(base_chica, tmp_path):
    import trimesh
    from vertebras.mallas import escribir_ply
    from vertebras.sintetico import _caja
    # una pieza continua (las vértebras sintéticas son primitivas superpuestas, ver limpiar_piezas)
    esfera = trimesh.creation.icosphere(subdivisions=3, radius=8.0)
    v, f = np.asarray(esfera.vertices), np.asarray(esfera.faces)
    cv, cf = _caja((60, 60, 60), (3, 3, 3))
    (tmp_path / "m").mkdir()
    escribir_ply(str(tmp_path / "m" / "sucia.ply"), np.vstack([v, cv]), np.vstack([f, cf + len(v)]))
    ruta = _metadata(tmp_path, ["a,m/sucia.ply,ESPAAA,I1,Cervical,3,Sí"])
    avisos = []
    indexar(ruta, str(tmp_path / "i.npz"), avisar=avisos.append, limpiar=True)
    assert "se quitó" in avisos[0] and "1 pieza suelta" in avisos[0]


def test_preseleccion_por_tamano(base_chica):
    from vertebras.indice import preseleccionar
    ind = cargar_indice(base_chica["indice"])
    e = ind["etiquetas"][5]
    par = next(j for j, x in enumerate(ind["etiquetas"]) if x[1] != e[1] and (x[0], x[3]) == (e[0], e[3]))
    validos = [j for j, x in enumerate(ind["etiquetas"]) if x[1] != e[1]]
    cfg.MAX_SIN_PRESELECCION, cfg.N_PRESELECCION = 10, 10
    sel = preseleccionar(ind["puntos"][5], ind, validos)
    assert len(sel) == 10 and par in sel and set(sel) <= set(validos)
    cfg.MAX_SIN_PRESELECCION = 1000
    assert preseleccionar(ind["puntos"][5], ind, validos) == validos
