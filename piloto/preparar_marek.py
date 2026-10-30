"""Prepara las vértebras cervicales de Marek et al. (2021) para el piloto de los pavos.

Datos: "Evolutionary versatility of the avian neck", Dryad, doi:10.5061/dryad.0k6djhb02 (CC0).
Bajar Meshes.zip desde la página de Dryad y extraer al menos las carpetas de ESPECIES.

Qué hace con cada malla:
- La pasa a mm (Turkey_Kambic viene en centímetros).
- La escribe como PLY binario con un nombre que incluye especie, individuo y posición.
- Excluye las vértebras que vienen partidas en varios archivos (Chicken C4).
- Arma metadata.csv con las columnas del protocolo.
No limpia las mallas: eso lo hace `python -m vertebras indexar --limpiar`.

Uso (desde la carpeta del proyecto):
  python piloto/preparar_marek.py <carpeta Meshes extraída> <carpeta de salida>
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from vertebras.mallas import escribir_ply, leer_malla  # noqa: E402

# carpeta de Meshes.zip -> (id_especie, id_individuo, factor para pasar a mm)
ESPECIES = {
    "Turkey": ("MELGAL", "MAREK-TURKEY0670", 1.0),
    "Turkey_Kambic": ("MELGAL", "MAREK-TURKEY-KAMBIC", 10.0),      # exportado en cm
    "Chicken": ("GALGAL", "MAREK-CHICKEN-EMB013", 1.0),
    "Guineafowl": ("AGENIG", "MAREK-GUINEAFOWL-EMB0GF", 1.0),
    "Ptarmigan": ("LAGLAG", "MAREK-PTARMIGAN-EMB0LL", 1.0),
    "TurkeyVulture": ("CATAUR", "MAREK-TURKEYVULTURE-LWH2008151", 1.0),
}


def main(entrada, salida):
    os.makedirs(os.path.join(salida, "mallas"), exist_ok=True)
    filas = []
    for carpeta, (especie, individuo, factor) in ESPECIES.items():
        origen = os.path.join(entrada, carpeta)
        if not os.path.isdir(origen):
            print(f"  falta la carpeta {carpeta}, se omite")
            continue
        for nombre in sorted(os.listdir(origen)):
            m = re.search(r"C(\d+)(_\w+)?\.(obj|ply)$", nombre, re.IGNORECASE)
            if not m:
                continue
            if m.group(2):
                print(f"  excluida (viene partida en varios archivos): {carpeta}/{nombre}")
                continue
            pos = int(m.group(1))
            v, f = leer_malla(os.path.join(origen, nombre))
            rel = f"mallas/{especie}_{individuo}_C{pos:02d}.ply"
            escribir_ply(os.path.join(salida, rel), v * factor, f)
            filas.append({"id_escaneo": f"{individuo}-C{pos:02d}", "archivo_liviano": rel,
                          "id_especie": especie, "id_individuo": individuo, "region": "Cervical",
                          "posicion": pos, "aprobado": "Sí"})
    if not filas:
        sys.exit(f"No se encontraron mallas en {entrada}")
    with open(os.path.join(salida, "metadata.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader(); w.writerows(filas)
    print(f"{len(filas)} vértebras en {salida}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
