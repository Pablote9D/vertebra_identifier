"""Parámetros del método. Los módulos los leen en el momento de usarlos, así que se pueden
cambiar en tiempo de ejecución (con `configurar` o asignando el atributo)."""

N_DENSO = 15000          # puntos muestreados por modelo (para medir distancias finas)
N_GRUESO = 300           # puntos usados en la etapa rápida de alineación
N_FINO = 2000            # puntos usados en la alineación fina
N_FINALISTAS = 12        # candidatas que pasan a la etapa fina
MAX_SIN_PRESELECCION = 200   # con más referencias disponibles se preseleccionan por tamaño
N_PRESELECCION = 75          # referencias que pasan a la alineación (ver README, bases grandes)
RECORTE_ICP = 0.9        # fracción de pares más cercanos usados en cada paso del ICP (motor scipy)
# Motor open3d: distancia máxima de correspondencia, como fracción del radio medio de la referencia
UMBRAL_GRUESO = 0.5
UMBRAL_FINO = 0.15
# Limpieza de mallas: una pieza suelta se conserva si está a menos de esto de la pieza principal
PIEZA_PEGADA_MM = 0.5

N_ORIENTACIONES = 24     # orientaciones iniciales de la etapa rápida (4 o 24)
MOTOR = "open3d"         # "open3d" u "scipy" (ICP propio con recorte de pares, el original)
ICP = "plano"            # con open3d: "punto" (punto a punto) o "plano" (punto a plano)


def configurar(motor=None, icp=None, orientaciones=None):
    global MOTOR, ICP, N_ORIENTACIONES
    if motor is not None:
        if motor not in ("open3d", "scipy"):
            raise ValueError(f"Motor desconocido: {motor}")
        MOTOR = motor
    if icp is not None:
        if icp not in ("punto", "plano"):
            raise ValueError(f"ICP desconocido: {icp}")
        ICP = icp
    if orientaciones is not None:
        if orientaciones not in (4, 24):
            raise ValueError("Las orientaciones iniciales deben ser 4 o 24")
        N_ORIENTACIONES = orientaciones


def estado():
    """Todos los parámetros (los nombres en mayúsculas), para pasarlos a otros procesos."""
    return {k: v for k, v in globals().items() if k.isupper()}


def aplicar(valores):
    """Fija los parámetros guardados con `estado`."""
    globals().update(valores)
