"""Regiones de la columna y códigos de posición (región + número dentro de la región)."""

import unicodedata

# nombre en la planilla (columna `region`) -> prefijo del código
REGIONES = {
    "Cervical": "C",
    "Torácica": "T",
    "Notario": "N",
    "Sinsacro": "SYN",
    "Caudal": "Ca",
    "Pigóstilo": "PYG",
}


def _normalizar(texto):
    """Minúsculas y sin tildes, para aceptar 'Toracica', 'TORÁCICA', etc."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.strip().lower()


_POR_CLAVE = {_normalizar(nombre): pref for nombre, pref in REGIONES.items()}


def prefijo(region):
    """Prefijo de código de una región (C, T, N, SYN, Ca, PYG). ValueError si no se reconoce."""
    try:
        return _POR_CLAVE[_normalizar(region)]
    except KeyError:
        raise ValueError(f"Región desconocida: {region!r}. Válidas: {', '.join(REGIONES)}") from None


def codigo(region, pos):
    """Código de posición, por ejemplo ('Cervical', 9) -> 'C09', ('Sinsacro', 1) -> 'SYN01'."""
    return f"{prefijo(region)}{int(pos):02d}"
