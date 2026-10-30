# Imagen del servidor para Cloud Run (ver DESPLEGAR.md).
FROM python:3.12-slim

# Open3D necesita estas librerías del sistema
RUN apt-get update \
 && apt-get install -y --no-install-recommends libegl1 libgl1 libgomp1 libusb-1.0-0 libidn2-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-servidor.txt ./
RUN pip install --no-cache-dir -r requirements-servidor.txt

COPY vertebras/ vertebras/
COPY web/ web/
# el índice y los nombres de las especies: ver DESPLEGAR.md
COPY datos/ datos/

ENV INDICE=/app/datos/indice.npz \
    ESPECIES=/app/datos/especies.csv \
    OMP_NUM_THREADS=1 \
    PORT=8080

CMD ["sh", "-c", "exec uvicorn --factory vertebras.servidor:crear_app --host 0.0.0.0 --port ${PORT}"]
