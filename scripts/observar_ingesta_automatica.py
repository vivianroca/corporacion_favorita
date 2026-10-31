"""Observa ciclos reales del scheduler; no dispara DAGs ni publica entregas."""

import json
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "docker/compose.yaml"]


def main():
    env = dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    base = f"http://127.0.0.1:{env.get('LAB1_AIRFLOW_PORT', '8082')}"
    request = Request(
        base + "/auth/token",
        data=json.dumps(
            {"username": "admin", "password": env["LAB1_AIRFLOW_ADMIN_PASSWORD"]}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        token = json.load(response)["access_token"]
    query = """import json,sqlite3
from pathlib import Path
rows=[]
for p in Path('/opt/lab1/operational/automatic').glob('*/control.sqlite'):
    with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
        rows.extend(json.loads(r[0]) for r in db.execute('SELECT result FROM cycles WHERE result IS NOT NULL ORDER BY as_of'))
print(json.dumps(rows))"""
    seen = set()
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        request = Request(
            base + "/api/v2/dags/lab1_ingesta_temporal/dagRuns?limit=100",
            headers={"Authorization": "Bearer " + token},
        )
        with urlopen(request, timeout=10) as response:
            runs = json.load(response)["dag_runs"]
        scheduled = {r["dag_run_id"]: r for r in runs if r["run_type"] == "scheduled"}
        output = subprocess.run(
            [*COMPOSE, "exec", "-T", "airflow-scheduler", "python", "-c", query],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        results = [
            r
            for r in json.loads(output.stdout)
            if scheduled.get(r["cycle_id"], {}).get("state") == "success"
        ]
        results.sort(key=lambda r: r["as_of"])
        for result in results:
            if result["cycle_id"] not in seen:
                print(json.dumps(result, sort_keys=True), flush=True)
                seen.add(result["cycle_id"])
        nonempty = [r for r in results if r["new_deliveries"] > 0]
        if len(nonempty) >= 2:
            idle = [
                r for r in results if r["as_of"] > nonempty[1]["as_of"] and r["new_deliveries"] == 0
            ]
            if idle:
                evidence = {
                    "scheduled_cycles": results,
                    "dag_runs": [
                        {
                            k: r[k]
                            for k in (
                                "dag_run_id",
                                "run_type",
                                "state",
                                "logical_date",
                                "start_date",
                                "end_date",
                            )
                        }
                        for r in scheduled.values()
                        if r["dag_run_id"] in seen
                    ],
                }
                target = ROOT / "data/automatic_demo/evidence.json"
                target.parent.mkdir(exist_ok=True)
                target.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
                print(
                    "Prueba completa: dos ciclos con datos y otro sin novedades. " + str(target),
                    flush=True,
                )
                return
        time.sleep(10)
    raise SystemExit(
        "Tiempo agotado: consultar estado del DAG y scheduler; no se dispararon runs manuales"
    )


if __name__ == "__main__":
    main()
