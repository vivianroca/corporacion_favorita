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
