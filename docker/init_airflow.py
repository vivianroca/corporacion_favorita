"""Inicializa exclusivamente los volúmenes y metadatos de lab1."""

import json
import os
import subprocess
from pathlib import Path

path = Path("/opt/airflow/auth/passwords.json")
credentials = {"admin": os.environ["LAB1_AIRFLOW_ADMIN_PASSWORD"]}
if not path.exists():
    path.write_text(json.dumps(credentials), encoding="utf-8")
    path.chmod(0o600)
elif json.loads(path.read_text()) != credentials:
    raise SystemExit("Las credenciales del volumen no coinciden con .env; no se sobrescriben")
subprocess.run(["airflow", "db", "migrate"], check=True)
if os.environ.get("LAB1_BOOTSTRAP_ENABLED") == "true":
    from reposicion.orchestration import bootstrap

    bootstrap(os.environ["LAB1_WORK_ROOT"])
