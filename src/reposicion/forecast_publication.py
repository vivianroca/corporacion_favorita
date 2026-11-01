"""Publicaciones inmutables y recuperables de pronósticos, independientes de Airflow."""

import argparse
import fcntl
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from reposicion.forecast_time import TIMEZONE, validate_origin
from reposicion.ingestion import _verify_bundle
from reposicion.snapshot_catalog import SnapshotCatalog, select_historical_snapshot, select_snapshot
from reposicion.source_io import canonical_bytes, checksum, parse_instant


def publication_id(identity):
    return hashlib.sha256(canonical_bytes(identity)).hexdigest()


def atomic_publish(output_root, identity, generate):
    """Lock persistente + rename atómico: reintentos no duplican ni sobrescriben."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    pid = publication_id(identity)
    with (root / ".publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target = root / pid
        if target.exists():
            manifest = _verify_bundle(target)
            if manifest["identity"] != identity:
                raise ValueError("Identidad de publicación alterada")
            return {"publication_id": pid, "path": str(target), "reused": True}
        with tempfile.TemporaryDirectory(prefix=".forecast-", dir=root) as temporary:
            stage = Path(temporary) / "bundle"
            stage.mkdir()
            generate(stage)
            files = {p.name: checksum(p) for p in stage.iterdir() if p.is_file()}
            manifest = {
                "schema_version": 1,
                "publication_id": pid,
                "identity": identity,
                "files": files,
            }
            (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
            _verify_bundle(stage)
            stage.rename(target)
        return {"publication_id": pid, "path": str(target), "reused": False}


def publish(
    work_root,
    output_root,
    origin,
    issued_at,
    uri,
    contracts_path,
    snapshot_id=None,
    model_version=None,
    use_snapshot_cutoff=False,
):
    from mlflow import MlflowClient

    from reposicion.uncertainty import artifact_bytes, run

    directory = (
        select_historical_snapshot(work_root, issued_at, contracts_path, snapshot_id)
        if use_snapshot_cutoff
        else select_snapshot(work_root, issued_at, snapshot_id)
    )
    if use_snapshot_cutoff:
        issued_at = json.loads((directory / "manifest.json").read_text())["as_of"]
        origin = str(parse_instant(issued_at).astimezone(ZoneInfo(TIMEZONE)).date())
    day = validate_origin(origin, issued_at)
    catalog = SnapshotCatalog(directory, contracts_path, day, issued_at)
    client = MlflowClient(tracking_uri=uri)
    name = "corporacion_favorita_random_forest"
    version = (
        client.get_model_version(name, str(model_version))
        if model_version
        else client.get_model_version_by_alias(name, "champion")
    )
    if version.status != "READY":
        raise ValueError("Champion no está READY")
    source = client.get_run(version.run_id)
    if source.info.status != "FINISHED" or source.data.params.get("feature_set") != "temporal_v2":
        raise ValueError("Champion incompatible con las variables temporales v2")
    calibration = []
    for r in client.search_runs(
        [source.info.experiment_id],
        filter_string="params.walk_forward_id = '" + source.data.params["walk_forward_id"] + "'",
        max_results=1000,
    ):
        p = r.data.params
        if (
            p.get("model") == "random_forest"
            and "window_index" in p
            and p["forecast_end"] < origin
            and parse_instant(p["evaluated_at"]) <= parse_instant(issued_at)
        ):
            payload = artifact_bytes(uri, r, "evaluation.csv")
            calibration.append(
                {"run_id": r.info.run_id, "sha256": hashlib.sha256(payload).hexdigest()}
            )
    identity = {
        "origin": origin,
        "issued_at": parse_instant(issued_at).isoformat(),
        "horizon_days": 7,
        "snapshot_id": directory.name,
        "snapshot_manifest_sha256": catalog.digest,
        "contracts_sha256": checksum(contracts_path),
        "model_name": name,
        "model_version": version.version,
        "model_run_id": version.run_id,
        "model_source": version.source,
        "calibration": sorted(calibration, key=lambda r: r["run_id"]),
        "code_sha256": {p.name: checksum(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
    }

    def generate(stage):
        with tempfile.TemporaryDirectory(prefix="inference-", dir=stage.parent) as temporary:
            result = Path(temporary) / "result"
            run(
                origin,
                issued_at,
                result,
                uri,
                catalog=catalog,
                model_version=version.version,
                contracts_path=contracts_path,
            )
            # Detecta modificaciones concurrentes antes de publicar.
            _verify_bundle(directory)
            if checksum(directory / "manifest.json") != catalog.digest:
                raise ValueError("Snapshot cambió durante inferencia")
            lineage = json.loads((result / "lineage.json").read_text())
            actual = sorted(
                [
                    {"run_id": r["run_id"], "sha256": r["sha256"]}
                    for r in lineage["residual_sources"]
                ],
                key=lambda r: r["run_id"],
            )
            if actual != identity["calibration"]:
                raise ValueError("La calibración cambió durante inferencia")
            lineage["publication_identity"] = identity
            (stage / "lineage.json").write_bytes(canonical_bytes(lineage))
            shutil.copyfile(result / "forecast_quantiles.csv", stage / "forecast_quantiles.csv")

    return atomic_publish(output_root, identity, generate)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("work-root", "output-root", "origin", "issued-at", "uri", "contracts-path"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--snapshot-id")
    p.add_argument("--model-version")
    p.add_argument("--use-snapshot-cutoff", action="store_true")
    args = p.parse_args()
    print(json.dumps(publish(**vars(args))))


if __name__ == "__main__":
    main()
