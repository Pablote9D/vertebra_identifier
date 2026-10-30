import pytest

from vertebras.regiones import REGIONES, codigo, prefijo


@pytest.mark.parametrize("region, pos, esperado", [
    ("Cervical", 9, "C09"),
    ("Torácica", 3, "T03"),
    ("Notario", 1, "N01"),
    ("Sinsacro", 1, "SYN01"),
    ("Caudal", 5, "Ca05"),
    ("Pigóstilo", 1, "PYG01"),
])
def test_codigos_del_protocolo(region, pos, esperado):
    assert codigo(region, pos) == esperado


@pytest.mark.parametrize("variante", ["toracica", "TORÁCICA", " Torácica ", "pigostilo"])
def test_acepta_mayusculas_y_sin_tildes(variante):
    assert prefijo(variante) in ("T", "PYG")


def test_seis_regiones():
    assert list(REGIONES.values()) == ["C", "T", "N", "SYN", "Ca", "PYG"]


def test_region_desconocida():
    with pytest.raises(ValueError, match="Región desconocida"):
        codigo("Lumbar", 2)
