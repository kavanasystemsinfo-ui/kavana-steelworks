# KAVANA Steelworks API — imagen de producción (Fly.io / Docker)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primero (cache de capas)
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

# Código de la app (rutas relativas al CONTEXTO RAÍZ del repo: este
# Dockerfile se construye con `docker build -f backend/Dockerfile .`)
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# Documentación del repo: corpus del asistente RAG (bots usuario + técnico).
# Sin estos archivos el asistente responde "no documentado" a todo.
# README/SECURITY van a la RAÍZ del contenedor (/) y docs/ a /docs, para que
# REPO_ROOT (parents[3] = /) encuentre tanto README.md como docs/adr y docs/specs.
COPY README.md SECURITY.md ./
COPY docs ./docs

# Entrypoint: aplica migraciones y arranca uvicorn
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

CMD ["/docker-entrypoint.sh"]
