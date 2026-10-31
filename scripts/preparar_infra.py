"""Prepara secretos locales sin mostrarlos ni descargar imágenes."""

import base64
import os
import secrets
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ["apache/airflow:3.3.2-python3.12", "postgres:16", "ghcr.io/mlflow/mlflow:v3.17.2"]


def main():
    if not (ROOT / "data/simulation/manifest.json").is_file():
        raise SystemExit("Falta la simulación existente; este comando no la regenera")
    for image in IMAGES:
        subprocess.run(["docker", "image", "inspect", image], check=True, stdout=subprocess.DEVNULL)
    path = ROOT / ".env"
    if path.exists():
        print("Se conserva .env existente; no se modificaron secretos ni puertos")
        return
    for port in (8082, 5011):
        with socket.socket() as connection:
            try:
                connection.bind(("127.0.0.1", port))
            except OSError as error:
                raise SystemExit(f"Puerto {port} no disponible: {error}") from error
    values = {
        "COMPOSE_PROJECT_NAME": "lab1",
        "LAB1_AIRFLOW_PORT": "8082",
        "LAB1_MLFLOW_PORT": "5011",
        "LAB1_POSTGRES_PASSWORD": secrets.token_hex(24),
        "LAB1_AIRFLOW_ADMIN_PASSWORD": secrets.token_hex(16),
        "LAB1_FERNET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "LAB1_API_SECRET": secrets.token_urlsafe(32),
        "LAB1_JWT_SECRET": secrets.token_urlsafe(32),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print(".env creado con secretos locales; puertos 8082 y 5011 verificados")


if __name__ == "__main__":
    main()
