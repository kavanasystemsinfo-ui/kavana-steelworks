#!/bin/sh
# Aplica migraciones Alembic, siembra la demo si la BD está vacía y arranca uvicorn.
# La BD se crea desde Fly (fly postgres) y la URL llega en DATABASE_URL / STEELWORKS_DATABASE_URL.
set -e

echo "[entrypoint] aplicando migraciones..."
alembic upgrade head

echo "[entrypoint] sembrando datos demo (idempotente)..."
python - <<'PY'
from sqlalchemy.orm import Session
from app.core.database import engine
from app.services.seed_demo import seed_demo

with Session(engine) as db:
    resultado = seed_demo(db)
    print(f"[seed] created={resultado['created']} tenant={resultado['tenant']}")
PY

echo "[entrypoint] arrancando uvicorn en 0.0.0.0:8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
