"""Pruebas aisladas: no entrenan modelos ni escriben runs en el servidor existente."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mlflow.system_metrics.metrics.cpu_monitor import CPUMonitor

from reposicion import system_metrics as tracking


@pytest.fixture
def fake_sdk(monkeypatch):
    client = Mock()
    start = Mock()
    events = []

    @contextmanager
    def active_run(**kwargs):
        start(**kwargs)
        events.append("run_started")
        try:
            yield SimpleNamespace(info=SimpleNamespace(run_id="isolated-test"))
        except Exception:
            events.append("failed")
            raise
        else:
            events.append("finished")

    monkeypatch.setattr(tracking.mlflow, "active_run", lambda: None)
    monkeypatch.setattr(tracking.mlflow, "get_tracking_uri", lambda: "http://previous")
    monkeypatch.setattr(tracking.mlflow, "set_tracking_uri", Mock())
    monkeypatch.setattr(
        tracking.mlflow, "set_experiment", lambda name: SimpleNamespace(experiment_id="test")
    )
    monkeypatch.setattr(tracking.mlflow, "start_run", active_run)
    monkeypatch.setattr(tracking, "MlflowClient", lambda **kwargs: client)
    return client, start, events


def test_enables_native_metrics_before_work_and_preserves_evaluation(
    fake_sdk, tmp_path, monkeypatch
):
    client, start, events = fake_sdk
    monkeypatch.setenv("MLFLOW_SYSTEM_METRICS_SAMPLING_INTERVAL", "10")
    monkeypatch.delenv("MLFLOW_SYSTEM_METRICS_SAMPLES_BEFORE_LOGGING", raising=False)
    for name in ("evaluation.csv", "real_vs_pronosticado.png", "distribucion_errores.png"):
        (tmp_path / name).write_bytes(b"isolated fixture")
    with tracking.training_run("http://unused", experiment_name="test", run_name="test") as run:
        assert events == ["run_started"]
        assert tracking.os.environ["MLFLOW_SYSTEM_METRICS_SAMPLING_INTERVAL"] == "1"
        run.log_results({"model": "test"}, {"mae": 1.5, "wape": 0.25}, tmp_path)
    start.assert_called_once_with(experiment_id="test", run_name="test", log_system_metrics=True)
    client.log_metric.assert_any_call("isolated-test", "mae", 1.5)
    client.log_metric.assert_any_call("isolated-test", "wape", 0.25)
    durations = [
        c.args[2]
        for c in client.log_metric.call_args_list
        if c.args[1] == "execution_duration_seconds"
    ]
    assert len(durations) == 1 and durations[0] >= 0
    assert client.log_artifact.call_count == 3
    assert events == ["run_started", "finished"]
    assert tracking.os.environ["MLFLOW_SYSTEM_METRICS_SAMPLING_INTERVAL"] == "10"
    assert "MLFLOW_SYSTEM_METRICS_SAMPLES_BEFORE_LOGGING" not in tracking.os.environ
    tracking.mlflow.set_tracking_uri.assert_any_call("http://previous")


def test_failure_still_records_elapsed_time_and_closes_run(fake_sdk):
    client, _, events = fake_sdk
    with (
        pytest.raises(ValueError, match="synthetic failure"),
        tracking.training_run("http://unused", experiment_name="test", run_name="test"),
    ):
        raise ValueError("synthetic failure")
    assert client.log_metric.call_args.args[1] == "execution_duration_seconds"
    assert events == ["run_started", "failed"]


@pytest.mark.parametrize("via_environment", [False, True])
def test_existing_active_run_is_never_reused(monkeypatch, via_environment):
    monkeypatch.setattr(
        tracking.mlflow, "active_run", lambda: None if via_environment else object()
    )
    if via_environment:
        monkeypatch.setenv("MLFLOW_RUN_ID", "existing-run")
    with (
        pytest.raises(RuntimeError, match="run activo"),
        tracking.training_run("http://unused", experiment_name="test", run_name="test"),
    ):
        pytest.fail("No debe entrar en un run preexistente")


def test_official_cpu_and_ram_collector_works_without_training():
    monitor = CPUMonitor()
    monitor.collect_metrics()
    metrics = monitor.aggregate_metrics()
    assert 0 <= metrics["cpu_utilization_percentage"] <= 100
    assert metrics["system_memory_usage_megabytes"] >= 0
    assert 0 <= metrics["system_memory_usage_percentage"] <= 100
