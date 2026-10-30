# Prototipo de identificación de vértebras de aves

Compara un modelo 3D de una vértebra contra una base de referencia y devuelve las candidatas más probables de especie y posición.

Es un prototipo para responder una pregunta: **¿la forma 3D alcanza para distinguir la posición de una vértebra?** Todavía no es una aplicación para usuarios.

## Requisitos

- Python 3.10 o posterior
- numpy, scipy, open3d y trimesh (probado con numpy 2.5, scipy 1.18, open3d 0.20 y trimesh 5.2, en Python 3.13)
- En Linux, Open3D necesita además la librería del sistema libEGL

```
pip install -r requirements.txt
sudo apt install libegl1        # solo Linux, si Open3D da "libEGL.so.1: cannot open shared object file"
```

Para correr los tests:

```
pip install -r requirements-dev.txt
pytest
```

## Cómo funciona

1. Cada malla se convierte en una nube de 15.000 puntos repartidos sobre la superficie. Para las referencias se guarda también la normal de la superficie en cada punto.
2. La nube se centra y se gira a sus ejes principales, para que todas queden en una orientación parecida.
3. **Etapa rápida:** la vértebra consultada se alinea con pocos puntos contra todas las de la base. Se prueban 24 orientaciones iniciales: los cuatro sentidos posibles de los ejes y además los casos en que los ejes quedan intercambiados (por ejemplo, cuando el largo y el ancho son parecidos).
4. **Etapa fina:** las 12 referencias más parecidas se realinean con más puntos y se mide la distancia media entre superficies, en mm.
5. Los resultados se agrupan por especie y posición y se ordenan por distancia.

La alineación usa ICP **punto a plano** de Open3D: minimiza la distancia de cada punto al plano tangente de la referencia, en lugar de al punto más cercano. Converge mejor, sobre todo con fragmentos. El ICP original (punto a punto, en numpy y scipy) sigue disponible con `--motor scipy` para comparar.

El tamaño se mantiene en mm a propósito: en las pruebas, normalizar el tamaño empeoró mucho los resultados.

## Uso

Todos los comandos se corren desde la carpeta del proyecto con `python -m vertebras`.

### 1. Probar con datos sintéticos

```
python -m vertebras sintetico --salida base_sintetica
python -m vertebras indexar --metadata base_sintetica/metadata.csv --salida indice.npz
python -m vertebras evaluar --indice indice.npz --muestra 50
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
| region | Cervical | Cervical, Torácica, Notario, Sinsacro, Caudal, Pigóstilo |
| posicion | 9 | Número dentro de la región |
| aprobado | Sí | Las filas con "No" se ignoran |

Las mallas deben estar en milímetros. Se leen PLY, OBJ, STL, OFF y glTF con Open3D, y otros formatos con trimesh.

Cada posición se muestra como región más número dentro de la región:

| Región | Código | Ejemplo |
| --- | --- | --- |
| Cervical | C | C09 |
| Torácica | T | T03 |
| Notario | N | N01 |
| Sinsacro | SYN | SYN01 |
| Caudal | Ca | Ca05 |
| Pigóstilo | PYG | PYG01 |

La región se acepta con o sin tilde y en mayúsculas o minúsculas. Si una fila aprobada tiene una región que no está en la lista, `indexar` se detiene e indica la fila, para que un error de tipeo no cree una clase aparte.

```
python -m vertebras indexar --metadata mis_datos/metadata.csv --salida indice.npz --limpiar
```

`--limpiar` quita de cada malla las piezas sueltas que no son parte de la vértebra: marcadores, restos de segmentación o basura del escaneo. Conserva la pieza principal y los parches pegados a ella (a menos de 0.5 mm), y descarta lo que está suelto o sobresale. Informa cuánto se quitó de cada archivo; si es más del 5% del área, pide revisar la malla. Conviene usarlo con escaneos y tomografías reales. No se debe usar con la base sintética: sus vértebras están armadas con cilindros y cajas superpuestos, y perderían partes.

### 3. Identificar una vértebra

```
python -m vertebras identificar pieza.ply --indice indice.npz --top 5 --umbral 0.63
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
- **--limpiar:** igual que en `indexar`, quita piezas sueltas de la pieza consultada.

### 4. Medir la precisión

```
python -m vertebras evaluar --indice indice.npz
python -m vertebras evaluar --indice indice.npz --recorte 0.3
```

Deja afuera un individuo entero por vez y trata de ubicar sus vértebras usando solo los demás. Informa especie correcta, posición exacta, posición con error de ±1 y acierto entre las 3 primeras.

También muestra una tabla por posición: cuántas consultas hubo, cuántas acertaron y qué posiciones eligió el método. Por ejemplo, `C07 ×1, C06 ×1` quiere decir que una C07 se identificó bien y otra como C06. "otra especie" cuenta las veces que la especie salió mal.

Las vértebras cuya especie y posición no aparecen en ningún otro individuo de la base no tienen respuesta posible. No se cuentan en los porcentajes y se listan aparte. Esto pasa, por ejemplo, si una especie tiene un solo individuo o si a un individuo le falta una posición.

- `--recorte 0.3` elimina el 30% de cada pieza consultada, para simular fragmentos de excavación. Cada consulta usa siempre el mismo corte, así que las corridas se pueden comparar entre sí.
- `--muestra N` evalúa solo N vértebras al azar, para pruebas rápidas. Con pocas consultas el resultado varía mucho (ver "Resultados").
- `--nucleos N` reparte las consultas en N procesos. Por defecto usa todos los núcleos. El resultado no depende de cuántos se usen.

### Opciones de alineación

`identificar` y `evaluar` aceptan:

| Opción | Valores | Por defecto |
| --- | --- | --- |
| `--motor` | `open3d`, `scipy` (el ICP original) | `open3d` |
| `--icp` | `plano` (punto a plano), `punto` (punto a punto); solo con `--motor open3d` | `plano` |
| `--orientaciones` | `24`, `4` | `24` |

## Estructura del proyecto

```
vertebras/          paquete
  config.py         parámetros y motor de alineación
  mallas.py         lectura y escritura de mallas
  preproceso.py     muestreo de superficie, marco PCA, normales, recorte, descriptor
  alineacion.py     ICP (motores open3d y scipy) y distancia entre superficies
  regiones.py       regiones y códigos de posición
  indice.py         construir, cargar y consultar el índice
  evaluacion.py     evaluación dejando un individuo afuera, en paralelo
  sintetico.py      base de prueba
  cli.py            línea de comandos
tests/              tests (pytest)
piloto/             piloto con tomografías publicadas de dos pavos (ver piloto/README.md)
```

Las funciones de `vertebras` devuelven datos y no imprimen nada, así que se pueden usar desde otro programa (por ejemplo, un servidor para la app):

```python
from vertebras.indice import cargar_indice, identificar

ind = cargar_indice("indice.npz")
for (especie, region, posicion), dist_mm, individuo, prob in identificar("pieza.ply", ind):
    ...
```

Los índices hechos con versiones anteriores siguen funcionando: si no tienen normales, se estiman al usarlos. Conviene volver a indexar para usar las normales exactas de la malla.

## Resultados hasta ahora

### Datos reales: dos pavos

Vértebras cervicales de dos pavos (*Meleagris gallopavo*) tomografiados en estudios distintos, del conjunto de datos de Marek et al. (2021). Se agregaron pollo, gallineta, perdiz nival y jote cabeza colorada como distractores. Cada vértebra de un pavo se busca entre las del otro: 22 consultas, de la C3 a la C13 en los dos sentidos. El detalle y cómo reproducirlo está en [piloto/README.md](piloto/README.md).

| Configuración | Especie | Posición exacta | Posición ±1 | Entre las 3 primeras |
| --- | --- | --- | --- | --- |
| Original (scipy, 4 orientaciones) | 100% | 86.4% | 100% | 100% |
| **Actual (Open3D punto a plano, 24 orientaciones)** | 100% | **86.4%** | **100%** | **100%** |
| Original, fragmentos (30% menos) | 86.4% | 27.3% | 63.6% | 68.2% |
| **Actual, fragmentos (30% menos)** | **95.5%** | **68.2%** | **86.4%** | **81.8%** |

- **La forma distingue la posición entre individuos distintos.** Con piezas enteras, los 3 errores son con la vértebra vecina (C7→C6, C8→C7, C11→C12), todos en la mitad del cuello, donde las vértebras más se parecen entre sí.
- **Con fragmentos, la configuración actual mantiene la mayoría de los aciertos;** la original pierde dos tercios.
- **Es una muestra muy chica:** 22 consultas, con una sola referencia correcta para cada una. Cada consulta que cambia mueve el resultado 4.5 puntos. Con fragmentos, dos preparaciones casi iguales de las mallas dieron 68% y 73% de posición exacta.
- **Acertar la especie acá es fácil**, porque los distractores son bastante más chicos que el pavo.

### Datos sintéticos

172 vértebras de 12 individuos, evaluando **las 172** dejando afuera el individuo de cada una. Tiempos en una máquina de 4 núcleos.

#### Pieza entera

| Configuración | Especie | Posición exacta | Posición ±1 | Entre las 3 primeras | Tiempo total |
| --- | --- | --- | --- | --- | --- |
| Original: scipy, 4 orientaciones, 1 núcleo | 50.0% | 27.3% | 38.4% | 50.6% | 381 s |
| scipy, 24 orientaciones | 52.3% | 30.8% | 41.3% | 53.5% | |
| Open3D punto a punto, 4 orientaciones | 50.0% | 28.5% | 39.5% | 51.2% | |
| Open3D punto a plano, 4 orientaciones | 48.8% | 28.5% | 38.4% | 52.9% | |
| **Actual: Open3D punto a plano, 24 orientaciones, 4 núcleos** | **51.2%** | **31.4%** | **40.7%** | **55.2%** | **257 s** |

#### Fragmentos (30% de la pieza eliminado)

| Configuración | Especie | Posición exacta | Posición ±1 | Entre las 3 primeras |
| --- | --- | --- | --- | --- |
| Original: scipy, 4 orientaciones | 38.4% | 10.5% | 17.4% | 27.9% |
| scipy, 24 orientaciones | 39.0% | 12.8% | 23.3% | 30.8% |
| Open3D punto a punto, 4 orientaciones | 35.5% | 8.7% | 18.0% | 28.5% |
| Open3D punto a plano, 4 orientaciones | 41.3% | 16.3% | 27.3% | 33.7% |
| **Actual: Open3D punto a plano, 24 orientaciones** | **43.6%** | **20.3%** | **29.1%** | **41.9%** |

#### Calidad de la alineación

Prueba aparte, sobre otra base sintética (semilla 7). Para 80 mallas se tomaron dos muestreos independientes de la misma pieza y se alineó uno contra el otro, sabiendo cuál es la respuesta correcta. "Registro correcto" significa que la alineación quedó tan bien como la verdadera (diferencia de distancia menor a 0.01 mm).

| Configuración | Pieza entera | Fragmento (30% menos) | Tiempo por par |
| --- | --- | --- | --- |
| Original: scipy, 4 orientaciones | 100% | 6% | 86 ms |
| Open3D punto a punto, 4 orientaciones | 100% | 9% | 48 ms |
| Open3D punto a plano, 4 orientaciones | 100% | 40% | 46 ms |
| Open3D punto a plano, 24 orientaciones | 100% | 64% | 59 ms |

#### Lectura de mallas

Una malla de 330.000 caras, del tamaño de un escaneo real:

| Formato | Lector anterior (hecho a mano) | Open3D |
| --- | --- | --- |
| PLY binario | 1.97 s | 0.03 s |
| PLY ASCII | 1.65 s | 0.10 s |
| OBJ | 0.65 s | 0.43 s |

#### Qué muestran

- **El ICP punto a plano es la mejora principal para fragmentos.** La posición exacta pasa de 10.5% a 20.3% y la alineación correcta de 6% a 64%. Con piezas enteras la alineación ya era buena con cualquier motor, por eso ahí la diferencia es chica.
- **Las 24 orientaciones suman unos 3 puntos de posición exacta.** Por consulta hacen 6 veces más alineaciones rápidas, pero con Open3D y la evaluación en paralelo la corrida completa igual tarda menos que la original.
- **El error principal es confundir las especies B y C** (unas 60 de 172 consultas, con cualquier motor). El generador las hace casi iguales a propósito; no es un problema de alineación.
- **Con pocas consultas los resultados engañan.** La versión anterior de este README daba 60% de especie y 44% de posición exacta con 25 consultas. Las mismas configuraciones dan 50% y 27% con las 172. Para comparar variantes hay que usar todas las consultas, o al menos más de 100.
- **Con recorte, el lugar del corte mueve los resultados unos ±3 puntos.**
- El umbral sugerido para "no se parece a nada" bajó de 0.68 a 0.63 mm, porque las alineaciones correctas quedan más ajustadas.

Normalizar el tamaño (prueba anterior, con 25 consultas) dio 12% de especie y 12% de posición exacta, contra 60% y 44% en mm en esa misma prueba.

## Limitaciones conocidas

- **Todavía no hay pruebas con el escáner de superficie propio.** El piloto real usa tomografías de dos pavos; falta repetirlo con escaneos propios y con 3 o más individuos por especie.
- **Las vértebras sintéticas son simétricas izquierda-derecha y también craneal-caudal**, así que girarlas 180° da la misma forma. Con ellas no se puede probar si el método distingue el extremo craneal del caudal.
- **`--limpiar` decide por distancia a la pieza principal.** Una vértebra que llegue partida en piezas separadas por más de 0.5 mm perdería las piezas menores; por eso informa cuánto quitó de cada malla.
- **Velocidad.** `evaluar` tarda ~1.5 s por consulta con 4 núcleos. `identificar` procesa una sola consulta en un núcleo y tarda unos 9 s con 170 referencias, contando la carga del índice. Casi todo el tiempo se va en la etapa rápida (24 orientaciones × cada referencia) y crece en proporción al tamaño de la base.
- La preselección con descriptor barato, que se activa en bases de más de 400 vértebras, funcionó mal en las pruebas y hay que reemplazarla. Con bases grandes también va a hacer falta para la velocidad.
- "Posición ±1" no cruza el límite entre regiones: confundir la última cervical con la primera torácica cuenta como error.
- No usa landmarks ni medidas con calibre; solo la superficie.
- Las probabilidades no están calibradas.
- Los umbrales del ICP de Open3D se ajustaron con datos sintéticos. Con escaneos reales conviene revisarlos (`UMBRAL_GRUESO` y `UMBRAL_FINO` en `vertebras/config.py`).

## Próximos pasos

1. Escanear 3 o más individuos de una misma especie con el escáner propio (la región cervical alcanza, unos 40 escaneos) y repetir el piloto.
2. Según los resultados, sumar landmarks o medidas como información adicional.
3. Reemplazar la preselección por descriptor, para bases grandes.
4. Acelerar una consulta individual (repartir la etapa rápida entre núcleos, o preseleccionar antes de alinear).

### Para la app

- **La comparación correría en un servidor.** Open3D y scipy no corren en iOS ni Android. La app captura y envía la pieza, y un servidor con este paquete hace la búsqueda. Así la base de referencia se actualiza sin publicar versiones nuevas de la app.
- **Escaneo con el celular.** El LiDAR de los teléfonos no tiene resolución suficiente para piezas de 10–20 mm. La fotogrametría con muchas fotos de cerca puede funcionar, pero hay que medir si la precisión alcanza: hoy las diferencias entre especies parecidas son de décimas de mm.
- **Escala.** Como el método trabaja en mm, una foto o un modelo de fotogrametría necesita una referencia de tamaño (regla o tarjeta de calibración junto a la pieza).
- **Identificación desde una foto.** Es otro problema: comparar una imagen 2D contra modelos 3D, por ejemplo generando vistas de la base desde muchos ángulos. Este prototipo no lo cubre; serviría para generar esas vistas.
