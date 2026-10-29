# Prototipo de identificación de vértebras de aves

Compara un modelo 3D de una vértebra contra una base de referencia y devuelve las candidatas más probables de especie y posición.

Es un prototipo para responder una pregunta: **¿la forma 3D alcanza para distinguir la posición de una vértebra?** Todavía no es una aplicación para usuarios.

## Requisitos

- Python 3.10 o posterior
- numpy y scipy
- Opcional: trimesh, para leer más formatos de malla (sin trimesh lee PLY y OBJ)

```
pip install numpy scipy
pip install trimesh   # opcional
```

## Cómo funciona

1. Cada malla se convierte en una nube de 15.000 puntos repartidos sobre la superficie.
2. La nube se centra y se gira a sus ejes principales, para que todas queden en una orientación parecida.
3. **Etapa rápida:** la vértebra consultada se alinea con pocos puntos contra todas las de la base. Se prueban los cuatro sentidos posibles de los ejes.
4. **Etapa fina:** las 12 referencias más parecidas se realinean con más puntos (ICP) y se mide la distancia media entre superficies, en mm.
5. Los resultados se agrupan por especie y posición y se ordenan por distancia.

El tamaño se mantiene en mm a propósito: en las pruebas, normalizar el tamaño empeoró mucho los resultados.

## Uso

### 1. Probar con datos sintéticos

```
python vertebras.py sintetico --salida base_sintetica
python vertebras.py indexar --metadata base_sintetica/metadata.csv --salida indice.npz
python vertebras.py evaluar --indice indice.npz --muestra 50
```

`sintetico` genera 3 especies con 4 individuos cada una. Las formas son muy simplificadas y la variación entre individuos es alta a propósito. Sirve para verificar que todo funciona, no para predecir la precisión con huesos reales.

### 2. Usar escaneos reales

Armar una carpeta con las mallas y una planilla `metadata.csv` con estas columnas (las mismas del documento de protocolo):

| Columna | Ejemplo | Notas |
| --- | --- | --- |
| id_escaneo | MUS-1234-C09 | |
| archivo_liviano | mallas/ANAPLA_MUS-1234_C09_v1.ply | Ruta relativa a la planilla |
| id_especie | ANAPLA | |
| id_individuo | MUS-1234 | La evaluación deja afuera individuos enteros |
| region | Cervical | Cervical, Torácica, Notario, Sinsacro, Caudal |
| posicion | 9 | Número dentro de la región |
| aprobado | Sí | Las filas con "No" se ignoran |

Las mallas deben estar en milímetros.

```
python vertebras.py indexar --metadata mis_datos/metadata.csv --salida indice.npz
```

### 3. Identificar una vértebra

```
python vertebras.py identificar pieza.ply --indice indice.npz --top 5 --umbral 0.5
```

Salida:

```
  Especie   Posición   Prob. rel.  Dist. (mm)  Individuo más parecido
  ESPBBB    C08              95%       0.155  ESPBBB-002
  ESPCCC    C11               3%       0.196  ESPCCC-003
```

- **Prob. rel.:** probabilidad relativa entre las candidatas mostradas. Todavía no está calibrada; sirve para ordenar, no como porcentaje de confianza real.
- **Dist. (mm):** distancia media entre superficies después de alinear. Menor es más parecido.
- **--umbral:** si la mejor distancia lo supera, avisa que puede no haber nada parecido en la base. El valor sugerido sale de `evaluar`.

### 4. Medir la precisión

```
python vertebras.py evaluar --indice indice.npz
python vertebras.py evaluar --indice indice.npz --recorte 0.3
```

Deja afuera un individuo entero por vez y trata de ubicar sus vértebras usando solo los demás. Informa especie correcta, posición exacta, posición con error de ±1 y acierto entre las 3 primeras.

`--recorte 0.3` elimina el 30% de cada pieza consultada, para simular fragmentos de excavación. `--muestra N` evalúa solo N vértebras al azar, para pruebas rápidas.

## Resultados hasta ahora

Con datos sintéticos (172 vértebras, 25 consultas):

| Prueba | Especie | Posición exacta | Posición ±1 |
| --- | --- | --- | --- |
| Tamaño en mm | 60% | 44% | 56% |
| Tamaño normalizado | 12% | 12% | 12% |

## Limitaciones conocidas

- Solo considera 4 orientaciones iniciales. Si los ejes principales de dos vértebras quedan intercambiados (por ejemplo, cuando el largo y el ancho son parecidos), la alineación puede fallar. Falta probar con las 24 rotaciones posibles.
- Es lento: unos 4 segundos por consulta con una base de 170 vértebras, en un solo núcleo.
- La preselección con descriptor barato, que se activa en bases de más de 400 vértebras, funcionó mal en las pruebas y hay que reemplazarla.
- No usa landmarks ni medidas con calibre; solo la superficie.
- Las probabilidades no están calibradas.

## Próximos pasos

1. Probar las 24 orientaciones iniciales.
2. Pasar a Open3D para ganar velocidad y usar ICP punto a plano.
3. Paralelizar la evaluación.
4. Probar con los primeros escaneos reales del caso 0.
5. Según los resultados, sumar landmarks o medidas como información adicional.
