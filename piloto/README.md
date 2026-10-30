# Piloto: dos pavos

Primera prueba con datos reales de la pregunta del prototipo: **¿la forma 3D alcanza para distinguir la posición de una vértebra?** Se compara cada vértebra cervical de un pavo contra las del otro.

## Datos

Marek, R. D., Falkingham, P. L., Benson, R. B. J., Gardiner, J. D., Maddox, T. W. y Bates, K. T. (2021). *Evolutionary versatility of the avian neck*. Proceedings of the Royal Society B 288: 20203150. Datos en Dryad, [doi:10.5061/dryad.0k6djhb02](https://doi.org/10.5061/dryad.0k6djhb02), licencia CC0.

Son modelos 3D de cada vértebra cervical, salvo el atlas, hechos a partir de tomografías. Las mallas no están en este repositorio: hay que bajar `Meshes.zip` (1.7 GB) desde la página de Dryad con un navegador.

Carpetas usadas:

| Carpeta | Especie | Individuo | Posiciones | Notas |
| --- | --- | --- | --- | --- |
| `Turkey` | *Meleagris gallopavo* | TURKEY0670 | C3–C14 | No figura en la planilla de ejemplares de Dryad |
| `Turkey_Kambic` | *Meleagris gallopavo* | Kambic | C2–C13 | En centímetros; trae flechas de un sistema de ejes y miles de fragmentos sueltos. No figura en la planilla |
| `Chicken` | *Gallus gallus domesticus* | EMB013 | C2–C14 | La C4 viene partida en dos archivos y se excluye |
| `Guineafowl` | *Agelastes niger* | EMB 0GF | C2–C14 | |
| `Ptarmigan` | *Lagopus lagopus* | EMB 0LL | C2–C14 | |
| `TurkeyVulture` | *Cathartes aura* | LWH 2008 151 | C2–C14 | |

Es la única especie del conjunto con dos individuos. Pollo, gallineta, perdiz nival y jote cabeza colorada actúan como distractores: no tienen otro individuo, así que sus vértebras no se cuentan como consultas, pero siguen en la base como candidatas.

## Cómo reproducirlo

Desde la carpeta del proyecto, con las carpetas de arriba extraídas de `Meshes.zip` en `Meshes/`:

```
python piloto/preparar_marek.py Meshes piloto_datos
python -m vertebras indexar --metadata piloto_datos/metadata.csv --salida piloto_datos/indice.npz --limpiar
python -m vertebras evaluar --indice piloto_datos/indice.npz
python -m vertebras evaluar --indice piloto_datos/indice.npz --recorte 0.3
```

`preparar_marek.py` pasa `Turkey_Kambic` a mm, renombra las mallas y arma `metadata.csv`. La limpieza de piezas sueltas la hace `indexar --limpiar`. En las vértebras de `Turkey_Kambic` quita entre 2% y 32% del área (32% en la C3, por las flechas); en las demás especies, menos del 5%. Se revisaron imágenes de las mallas limpias: las vértebras quedan completas.

La conversión a mm se verificó comparando el largo de cada posición entre los dos pavos: el cociente da entre 0.90 y 1.09.

Para la configuración original, agregar `--motor scipy --orientaciones 4` a `evaluar`.

## Resultados

22 consultas: cada posición de C3 a C13 de cada pavo, buscada entre las del otro. La C14 del pavo 0670 y la C2 del de Kambic no tienen par en el otro individuo y no se cuentan.

| Configuración | Especie | Posición exacta | Posición ±1 | Entre las 3 primeras |
| --- | --- | --- | --- | --- |
| Original (scipy, 4 orientaciones) | 100% | 86.4% | 100% | 100% |
| **Actual (Open3D punto a plano, 24 orientaciones)** | 100% | **86.4%** | **100%** | **100%** |
| Original, fragmentos (30% menos) | 86.4% | 27.3% | 63.6% | 68.2% |
| **Actual, fragmentos (30% menos)** | **95.5%** | **68.2%** | **86.4%** | **81.8%** |

Por posición, configuración actual y piezas enteras:

| Posición | Consultas | Exacta | Predicciones |
| --- | --- | --- | --- |
| C03 – C06 | 8 | 100% | todas correctas |
| C07 | 2 | 50% | C07, C06 |
| C08 | 2 | 50% | C08, C07 |
| C09, C10 | 4 | 100% | todas correctas |
| C11 | 2 | 50% | C12, C11 |
| C12, C13 | 4 | 100% | todas correctas |

## Qué se puede concluir

- **La forma distingue la posición entre dos individuos distintos**, aunque se tomografiaron en estudios distintos y uno vino en otra unidad. Con piezas enteras, todos los errores son con la vértebra vecina, en la mitad del cuello, y en esos casos la posición correcta queda segunda, a 0.03 mm o menos.
- **Con fragmentos hace falta la configuración actual.** La original baja a 27% de posición exacta y comete errores grandes (una C13 identificada como C4).

## Qué no se puede concluir

- **La muestra es muy chica.** Son 22 consultas, cada una con una sola referencia correcta. Una consulta que cambia mueve el resultado 4.5 puntos. El 86% de posición exacta tiene un intervalo de confianza de aproximadamente 65–97%. Con fragmentos, dos preparaciones casi iguales de las mallas dieron 68% y 73%.
- **Acertar la especie es fácil acá:** los pavos miden 20–35 mm y los distractores son más chicos. No prueba que se distingan especies de tamaño parecido.
- **Son tomografías.** Falta probar con el escáner de superficie propio.
