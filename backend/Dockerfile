# KAVANA Steelworks API — imagen de producción (Fly.io / Docker)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primero (cache de capas)
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Código de la app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Entrypoint: aplica migraciones y arranca uvicorn
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

CMD ["/docker-entrypoint.sh"]
