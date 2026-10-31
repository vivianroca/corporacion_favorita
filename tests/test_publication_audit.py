import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "publication_audit", Path(__file__).resolve().parents[1] / "scripts/auditar_publicacion.py"
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


@pytest.mark.parametrize(
    "path",
    [
        "data/original/train.csv",
        "export.csv",
        "cache/state.sqlite-wal",
        "docker/volumes/db",
        ".env",
        "docker/.env.local",
        "models/model.joblib",
        "credentials/private.key",
    ],
)
def test_forbidden_files_block_publication(path):
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob(path, b"example")


def test_known_secret_is_detected_without_disclosing_it():
    secret = b"sentinel-for-the-unit-test"
    with pytest.raises(AUDIT.AuditError) as raised:
        AUDIT.validate_blob("README.md", secret, secrets=[secret])
    assert secret.decode() not in str(raised.value)


@pytest.mark.parametrize(
    "content",
    [
        b"ghp_" + b"A" * 36,
        b"AKIA" + b"A" * 16,
        b"-----BEGIN " + b"PRIVATE KEY-----",
    ],
)
def test_token_and_private_key_signatures_are_rejected(content):
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob("notes.txt", content)


def test_templates_cannot_contain_password_values():
    AUDIT.validate_blob(".env.example", b"LAB1_AIRFLOW_PORT=8082\nLAB1_API_SECRET=\n")
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob(".env.example", b"LAB1_API_SECRET=not-a-blank-value\n")


def test_large_blobs_and_symlinks_are_rejected():
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob("large.txt", b"x" * (AUDIT.MAX_BYTES + 1))
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob("link", b"../data", mode="120000")


def test_normal_source_and_documentation_are_allowed():
    AUDIT.validate_blob("src/reposicion/ingestion.py", b"print('example')\n")
    AUDIT.validate_blob("docs/report.md", b"SHA-256: " + b"a" * 64)


@pytest.mark.parametrize("name", ["train", "stores", "holidays_events", "oil", "transactions"])
def test_only_valid_pointers_for_required_originals_are_allowed(name):
    import yaml

    content = yaml.safe_dump(
        {"outs": [{"md5": "a" * 32, "size": 123, "hash": "md5", "path": name + ".csv"}]}
    ).encode()
    AUDIT.validate_blob(f"data/original/{name}.csv.dvc", content)


@pytest.mark.parametrize(
    "path",
    [
        "data/original/test.csv.dvc",
        "data/original/sample_submission.csv.dvc",
        "data/simulation.dvc",
        ".dvc/cache/object",
        ".dvc/config.local",
        ".dvc/tmp/state",
    ],
)
def test_other_data_and_dvc_private_state_remain_blocked(path):
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob(path, b"not allowed")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"date,sales\n2017-01-01,10\n",
        b"outs: []\n",
        b"outs:\n- md5: bad\n  size: 123\n  path: train.csv\n",
        b"outs:\n- md5: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n  size: 123\n  path: other.csv\n",
    ],
)
def test_pointer_exception_cannot_hide_raw_data_or_wrong_targets(content):
    with pytest.raises(AUDIT.AuditError):
        AUDIT.validate_blob("data/original/train.csv.dvc", content)


def test_gitignore_keeps_dvc_parents_traversable_without_exposing_data():
    import subprocess

    root = Path(__file__).resolve().parents[1]

    def ignored(path):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", "--", path], cwd=root, check=False
        )
        assert result.returncode in {0, 1}
        return result.returncode == 0

    assert not ignored("data/")
    assert not ignored("data/original/")
    for name in ["train", "stores", "holidays_events", "oil", "transactions"]:
        assert not ignored(f"data/original/{name}.csv.dvc")
        assert ignored(f"data/original/{name}.csv")
    assert ignored("data/original/test.csv")
    assert ignored("data/original/sample_submission.csv")
    assert ignored("data/simulation/manifest.json")
