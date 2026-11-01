"""Restauración y fallos recuperables con cliente en memoria, sin fit ni servicios."""

import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest
from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_DOES_NOT_EXIST

from reposicion import champion_restore as restore
from reposicion.source_io import canonical_bytes, checksum


def reseal(bundle):
    identity = {
        "schema_version": 1,
        "files": {p: checksum(bundle / p) for p in sorted(restore.FILES)},
    }
    manifest = {**identity, "bundle_id": hashlib.sha256(canonical_bytes(identity)).hexdigest()}
    (bundle / "manifest.json").write_bytes(canonical_bytes(manifest))


@pytest.fixture
def bundle(tmp_path):
    model = tmp_path / restore.MODEL_PATH
    model.parent.mkdir(parents=True)
    model.write_bytes(b"existing weights; never fit")
    pointer = tmp_path / "models/current.dvc"
    pointer.write_text("existing pointer")
    output = tmp_path / "bundle"
    (output / "calibration").mkdir(parents=True)
    runs = []
    for i in range(1, 5):
        start = date(2017, 1, 8) + timedelta(weeks=i - 1)
        evaluation = f"calibration/fold_{i}.csv"
        (output / evaluation).write_text(
            "date,store_nbr,family,actual,prediction\n"
            + "".join(f"{start},{store},A,12,10\n" for store in range(30))
        )
        runs.append(
            {
                "source_run_id": f"{i:032x}",
                "params": {
                    "window_index": str(i),
                    "model": "random_forest",
                    "feature_set": "temporal_v2",
                    "walk_forward_id": "original-group",
                    "forecast_start": str(start),
                    "forecast_end": str(start + timedelta(days=6)),
                    "training_end": str(start - timedelta(days=1)),
                    "evaluated_at": "2017-03-03T12:00:00Z",
                },
                "metrics": {"observations": 30, "mae": 2, "wape": 1 / 6, "actual_sales_sum": 360},
                "evaluation": evaluation,
            }
        )
    metadata = {
        "model_name": restore.NAME,
        "source_version": "4",
        "source_run_id": runs[-1]["source_run_id"],
        "source_model_uri": "models:/original",
        "source_experiment": "original",
        "model_tags": {"champion.dvc_pointer": "models/current.dvc"},
        "model": {
            "path": restore.MODEL_PATH,
            "sha256": checksum(model),
            "dvc_pointer": "models/current.dvc",
            "dvc_pointer_sha256": checksum(pointer),
        },
        "packages": {},
        "runs": runs,
    }
    (output / "metadata.json").write_bytes(canonical_bytes(metadata))
    (output / "probe.json").write_bytes(
        canonical_bytes({"input": {"columns": ["x"], "data": [[1.0]]}, "prediction": [10.0]})
    )
    reseal(output)
    return output, tmp_path


class Client:
    tracking_uri = "http://restore-unit-test.invalid"

    def __init__(self):
        self.runs, self.artifacts, self.versions, self.aliases = {}, {}, [], {}
        self.experiment = None
        self.registered = False
        self.fail_version_once = False

    def get_registered_model(self, name):
        if not self.registered:
            raise MlflowException("missing", error_code=RESOURCE_DOES_NOT_EXIST)
        return NS(name=name)

    def create_registered_model(self, name):
        self.registered = True

    def search_model_versions(self, query):
        return self.versions

    def get_experiment_by_name(self, name):
        return self.experiment

    def create_experiment(self, name):
        self.experiment = NS(experiment_id="1")
        return "1"

    def search_runs(self, ids, filter_string, **kwargs):
        sid = re.search("= '([^']+)'", filter_string)[1]
        return [r for r in self.runs.values() if r.data.tags["restore.source_run_id"] == sid]

    def create_run(self, eid, tags):
        rid = f"restored-{len(self.runs)}"
        run = NS(
            info=NS(run_id=rid, status="RUNNING"), data=NS(tags=dict(tags), params={}, metrics={})
        )
        self.runs[rid] = run
        return run

    def log_param(self, rid, key, value):
        self.runs[rid].data.params[key] = value

    def log_metric(self, rid, key, value):
        self.runs[rid].data.metrics[key] = value

    def log_artifact(self, rid, filename):
        self.artifacts[rid, Path(filename).name] = Path(filename).read_bytes()

    def log_artifacts(self, rid, directory, artifact_path):
        for p in Path(directory).rglob("*"):
            if p.is_file():
                self.artifacts[rid, artifact_path + "/" + str(p.relative_to(directory))] = (
                    p.read_bytes()
                )

    def set_tag(self, rid, key, value):
        self.runs[rid].data.tags[key] = value

    def set_terminated(self, rid, status):
        self.runs[rid].info.status = status

    def get_run(self, rid):
        return self.runs[rid]

    def download_artifacts(self, rid, artifact, directory):
        if artifact == "model":
            target = Path(directory) / "model"
            target.mkdir()
            (target / "model.pkl").write_bytes(self.artifacts[rid, "model/model.pkl"])
            return str(target)
        target = Path(directory) / Path(artifact).name
        target.write_bytes(self.artifacts[rid, artifact])
        return str(target)

    def create_model_version(self, name, source, run_id, tags, **kwargs):
        if self.fail_version_once:
            self.fail_version_once = False
            raise RuntimeError("interrupted before registration")
        version = NS(version="1", run_id=run_id, status="READY", tags=tags)
        self.versions.append(version)
        return version

    def set_registered_model_alias(self, name, alias, version):
        self.aliases[alias] = version


@pytest.fixture
def client(monkeypatch):
    client = Client()
    monkeypatch.setattr(restore.mlflow, "MlflowClient", lambda **kwargs: client)

    def save(bundle, root, target, rid):
        target.mkdir()
        (target / "model.pkl").write_bytes(b"already trained")

    monkeypatch.setattr(restore, "package_model", save)
    monkeypatch.setattr(
        restore.mlflow.pyfunc,
        "load_model",
        lambda *args, **kwargs: NS(predict=lambda frame: np.array([10.0])),
    )
    return client


def test_restore_is_idempotent_and_preserves_source_lineage(bundle, client):
    path, root = bundle
    first = restore.restore(path, client.tracking_uri, root, root / "locks")
    second = restore.restore(path, client.tracking_uri, root, root / "locks")
    assert first == second
    assert len(client.runs) == 4 and len(client.versions) == 1
    assert client.aliases == {"champion": "1"}
    assert first["source_version"] == "4" and first["trained"] is False
    for source, rid in first["run_mapping"].items():
        run = client.runs[rid]
        assert run.data.tags["restore.source_run_id"] == source
        assert run.info.status == "FINISHED"
        assert (rid, "evaluation.csv") in client.artifacts


def test_interrupted_registration_resumes_without_duplicate_runs(bundle, client):
    path, root = bundle
    client.fail_version_once = True
    with pytest.raises(RuntimeError, match="interrupted"):
        restore.restore(path, client.tracking_uri, root, root / "locks")
    assert not client.aliases
    restore.restore(path, client.tracking_uri, root, root / "locks")
    assert len(client.runs) == 4 and len(client.versions) == 1


def test_foreign_registry_is_not_overwritten(bundle, client):
    path, root = bundle
    client.registered = True
    client.versions = [NS(tags={})]
    with pytest.raises(ValueError, match="ajenas"):
        restore.restore(path, client.tracking_uri, root, root / "locks")
    assert not client.runs and not client.aliases


@pytest.mark.parametrize("target", ["model", "calibration", "extra", "link"])
def test_invalid_bundle_fails_before_remote_writes(bundle, client, target):
    path, root = bundle
    if target == "model":
        (root / restore.MODEL_PATH).write_bytes(b"changed")
    elif target == "calibration":
        (path / "calibration/fold_1.csv").write_text("corrupt")
    elif target == "extra":
        (path / "credentials.json").write_text("must not be accepted")
    else:
        (path / "extra").symlink_to(path / "metadata.json")
    with pytest.raises(ValueError):
        restore.restore(path, client.tracking_uri, root, root / "locks")
    assert not client.runs and not client.aliases


def test_future_training_is_rejected_even_with_valid_checksums(bundle):
    path, root = bundle
    metadata = json.loads((path / "metadata.json").read_text())
    metadata["runs"][0]["params"]["training_end"] = "2017-12-31"
    (path / "metadata.json").write_bytes(canonical_bytes(metadata))
    reseal(path)
    with pytest.raises(ValueError, match="temporal"):
        restore.verify_bundle(path, root)


def test_corrupted_remote_residuals_are_not_silently_replaced(bundle, client):
    path, root = bundle
    restored = restore.restore(path, client.tracking_uri, root, root / "locks")
    rid = next(iter(restored["run_mapping"].values()))
    client.artifacts[rid, "evaluation.csv"] = b"corrupt"
    with pytest.raises(ValueError, match="Residuos"):
        restore.restore(path, client.tracking_uri, root, root / "locks")
    assert len(client.runs) == 4 and len(client.versions) == 1


def test_corrupted_remote_weights_are_detected(bundle, client):
    path, root = bundle
    restored = restore.restore(path, client.tracking_uri, root, root / "locks")
    client.artifacts[restored["run_mapping"][f"{4:032x}"], "model/model.pkl"] = b"corrupt"
    with pytest.raises(ValueError, match="Pesos publicados"):
        restore.restore(path, client.tracking_uri, root, root / "locks")
