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
# --proxy-headers + --forwarded-allow-ips: tras el edge de Fly.io, request.client.host
# refleja la IP real del cliente (X-Forwarded-For) para que el rate limit sea efectivo.
# Trust boundary documentada en ADR-016: solo entra tráfico por el edge de Fly.
# El valor es configurable (FORWARDED_ALLOW_IPS); "*" sigue siendo válido porque
# el contenedor no expone puertos más allá del proxy de Fly.
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="$FORWARDED_ALLOW_IPS"
