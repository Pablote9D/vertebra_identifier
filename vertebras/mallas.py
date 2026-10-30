"""Lectura y escritura de mallas."""

import os
import struct

import numpy as np

_FORMATOS_O3D = (".ply", ".obj", ".stl", ".off", ".gltf", ".glb")


def o3d():
    """Importa Open3D sin sus mensajes de aviso."""
    import open3d
    open3d.utility.set_verbosity_level(open3d.utility.VerbosityLevel.Error)
    return open3d


def leer_malla(ruta):
    """Devuelve (vertices Nx3, caras Mx3 o None). Usa Open3D para PLY, OBJ, STL, OFF y glTF
    (el orden de los vértices puede cambiar, la geometría no) y trimesh para el resto."""
    if not os.path.isfile(ruta):
        raise FileNotFoundError(ruta)
    if os.path.splitext(ruta)[1].lower() in _FORMATOS_O3D:
        m = o3d().io.read_triangle_mesh(ruta)
        v, f = np.asarray(m.vertices, dtype=float), np.asarray(m.triangles, dtype=int)
        if len(v):
            return v, (f if len(f) else None)
    import trimesh                      # Open3D no lo entendió, o es otro formato
    m = trimesh.load(ruta, force="mesh", process=False)
    caras = np.asarray(m.faces, dtype=int) if len(getattr(m, "faces", [])) else None
    v = np.asarray(m.vertices, dtype=float)
    if not len(v):
        raise ValueError(f"No se pudo leer la malla: {ruta}")
    return v, caras


def escribir_ply(ruta, v, f):
    with open(ruta, "wb") as fh:
        cab = ("ply\nformat binary_little_endian 1.0\n"
               f"element vertex {len(v)}\nproperty float x\nproperty float y\nproperty float z\n"
               f"element face {len(f)}\nproperty list uchar int vertex_indices\nend_header\n")
        fh.write(cab.encode("ascii"))
        fh.write(np.asarray(v, "<f4").tobytes())
        for tri in f:
            fh.write(struct.pack("<B3i", 3, *tri))
