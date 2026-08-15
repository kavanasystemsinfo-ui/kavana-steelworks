#!/bin/sh
# Aplica migraciones Alembic contra la BD de producción y arranca uvicorn.
# La BD se crea desde Fly (fly postgres) y la URL llega en STEELWORKS_DATABASE_URL.
set -e

echo "[entrypoint] aplicando migraciones..."
alembic upgrade head

echo "[entrypoint] arrancando uvicorn en 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
