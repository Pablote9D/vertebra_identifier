"""Identificación de vértebras de aves por comparación de modelos 3D.

Módulos:
  config       parámetros y motor de alineación
  mallas       lectura y escritura de mallas
  preproceso   muestreo de superficie, marco PCA, normales, recorte, descriptor
  alineacion   ICP (motores open3d y scipy) y distancia entre superficies
  regiones     regiones de la columna y códigos de posición (C, T, N, SYN, Ca, PYG)
  indice       construir, cargar y consultar el índice de referencia
  evaluacion   evaluación dejando un individuo afuera
  sintetico    base de prueba con vértebras sintéticas
  cli          línea de comandos (python -m vertebras)
"""
