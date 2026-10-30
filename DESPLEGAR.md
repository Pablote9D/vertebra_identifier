# Publicar la app en Google Cloud Run

Un solo servicio sirve la página (carpeta `web/`) y la API (`vertebras/servidor.py`). Cloud Run lo apaga cuando nadie lo usa y lo vuelve a prender con la siguiente visita, así que con poco uso el costo es cero o casi cero.

## Lo que se necesita una sola vez

1. **Una cuenta de Google Cloud con facturación activada.** Cloud Run pide una tarjeta aunque el uso quede dentro del nivel gratuito.
2. **Un proyecto**, por ejemplo `osteoave`, creado en la consola de Google Cloud.
3. **La herramienta `gcloud`** instalada en la computadora desde la que se publica ([instrucciones](https://cloud.google.com/sdk/docs/install)), y luego:

   ```
   gcloud auth login
   gcloud config set project osteoave
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   ```

4. **Un aviso de presupuesto**, para enterarse si algo se descontrola: en la consola, Facturación → Presupuestos y alertas → Crear presupuesto, por ejemplo de 5 USD por mes con avisos al 50% y al 100%. El aviso no corta el servicio; solo manda un correo.

## Preparar la colección

La imagen lleva la colección de referencia en la carpeta `datos/`, que no está en git:

```
python -m vertebras verificar --metadata mis_datos/metadata.csv
python -m vertebras indexar --metadata mis_datos/metadata.csv --salida datos/indice.npz --limpiar
python -m vertebras evaluar --indice datos/indice.npz
```

`evaluar` sugiere al final un umbral para "no se parece a nada" (en el piloto, 0.93 mm); se usa abajo como `UMBRAL_MM`. Si la colección todavía no tiene dos individuos de ninguna especie, `evaluar` no puede sugerirlo: se puede dejar sin umbral.

Los nombres que muestra la app salen de `datos/especies.csv`:

```
id_especie,nombre_comun,nombre_cientifico
MELGAL,Pavo,Meleagris gallopavo
VULGRY,Cóndor andino,Vultur gryphus
```

Una especie que no esté en este archivo se muestra con su código.

## Publicar (y cada vez que cambie el código o la colección)

Desde la carpeta del proyecto:

```
gcloud run deploy osteoave --source . --region us-central1 --allow-unauthenticated --memory 1Gi --cpu 1 --concurrency 1 --max-instances 2 --timeout 120 --cpu-boost --set-env-vars UMBRAL_MM=0.93
```

Al terminar, `gcloud` muestra la dirección de la app (algo como `https://osteoave-xxxxx-uc.a.run.app`).

Qué hace cada opción:

| Opción | Por qué |
| --- | --- |
| `--source .` | Sube la carpeta y la construye con el `Dockerfile`. Lo que se sube lo decide `.gcloudignore`, que sí incluye `datos/` |
| `--region us-central1` | Región de precios más bajos. `southamerica-east1` (San Pablo) queda más cerca de Argentina pero es más cara; la diferencia de distancia casi no se nota frente a los segundos que tarda la comparación |
| `--allow-unauthenticated` | Cualquiera con la dirección puede usar la app. Sacarlo para que solo entren cuentas autorizadas |
| `--memory 1Gi` | Con 76 vértebras usa unos 300 MB. Cada vértebra suma alrededor de 1 MB: con más de unas 600, pasar a `2Gi` |
| `--cpu 1 --concurrency 1` | Cada comparación ocupa un núcleo entero durante unos 6 s; con una consulta por instancia no se pisan |
| `--max-instances 2` | Tope de costo: como mucho dos comparaciones al mismo tiempo. Las demás esperan |
| `--timeout 120` | Margen para archivos grandes |
| `--cpu-boost` | Más CPU al arrancar: el primer pedido después de un rato sin uso tarda menos |

## Qué esperar

- **Primera visita después de un rato sin uso:** unos segundos más mientras el servicio arranca (en las pruebas, 4.6 s hasta estar listo).
- **Cada comparación:** unos 6 a 7 s con 1 núcleo, con la colección actual. Con colecciones de más de 200 vértebras el tiempo se mantiene, porque solo se alinea contra las 75 de tamaño más parecido.
- **Archivos de hasta 30 MB.** Cloud Run no acepta envíos de más de 32 MB. Un PLY binario de 300.000 triángulos pesa unos 6 MB; un OBJ del mismo tamaño, bastante más.
- **Los archivos subidos no se guardan:** se procesan en una carpeta temporal y se borran al terminar. Los registros de Cloud Run guardan la hora, la dirección pedida y si hubo error, pero no el archivo.

## Costo

Con el nivel gratuito de Cloud Run (al momento de escribir esto, 240.000 segundos de CPU por mes; ver la [página de precios](https://cloud.google.com/run/pricing)), unas pocas miles de consultas por mes no deberían costar nada. A eso se suma el almacenamiento de las imágenes construidas en Artifact Registry, que puede tener un costo chico: conviene borrar las versiones viejas de vez en cuando desde la consola.

## Probar la imagen en la computadora antes de publicar

Con Docker instalado:

```
docker build -t osteoave .
docker run --rm -p 8080:8080 -e UMBRAL_MM=0.93 osteoave
```

Y abrir http://localhost:8080.

Sin Docker, con Python:

```
pip install -r requirements-servidor.txt
INDICE=datos/indice.npz ESPECIES=datos/especies.csv uvicorn --factory vertebras.servidor:crear_app --port 8080
```
