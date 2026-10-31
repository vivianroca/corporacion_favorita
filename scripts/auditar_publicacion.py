"""Audita archivos, índice o historial Git sin imprimir secretos ni publicar nada."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

import yaml

MAX_BYTES = 1024 * 1024
DVC_ORIGINALS = {"train", "stores", "holidays_events", "oil", "transactions"}
DVC_POINTERS = {f"data/original/{name}.csv.dvc" for name in DVC_ORIGINALS}
FORBIDDEN_DIRS = {
    "data",
    "models",
    "forecasts",
    "orders",
    "reports",
    "manifests",
    "logs",
    "volumes",
    "pgdata",
    "mlruns",
    "mlartifacts",
    ".venv",
    ".aws",
    ".ssh",
    "secrets",
}
FORBIDDEN_SUFFIXES = {
    ".csv",
    ".tsv",
    ".parquet",
    ".arrow",
    ".feather",
    ".pkl",
    ".pickle",
    ".joblib",
    ".onnx",
    ".h5",
    ".pt",
    ".pth",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".duckdb",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
}
TOKEN_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{36,255}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,255}"),
    re.compile(rb"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


class AuditError(ValueError):
    """No se debe publicar el contenido auditado."""


def private_values(root):
    path = root / ".env"
    values = []
    if path.is_file():
        for line in path.read_text().splitlines():
            key, separator, value = line.partition("=")
            value = value.strip().strip("\"'")
            if (
                separator
                and re.search(r"PASSWORD|SECRET|FERNET|TOKEN|PRIVATE|ACCESS_KEY", key)
                and len(value) >= 12
                and "${" not in value
            ):
                values.append(value.encode())
    return values


def validate_blob(path, content, *, mode="100644", secrets=(), path_only=False):
    parts = PurePosixPath(path)
    if mode == "120000":
        raise AuditError(f"{path}: enlace simbólico no permitido en la publicación")
    dvc_metadata = path in DVC_POINTERS or path == "data/original/.gitignore"
    if set(parts.parts) & FORBIDDEN_DIRS and not dvc_metadata:
        raise AuditError(f"{path}: directorio de datos, artefactos o secretos")
    if path.startswith(".dvc/") and path not in {".dvc/config", ".dvc/.gitignore"}:
        raise AuditError(f"{path}: caché, estado o configuración privada de DVC")
    name = parts.name.lower()
    if name != ".env.example" and (name == ".env" or name.startswith(".env.")):
        raise AuditError(f"{path}: archivo de entorno privado")
    if path not in DVC_POINTERS and (
        {s.lower() for s in parts.suffixes} & FORBIDDEN_SUFFIXES
        or re.search(r"\.(?:db|sqlite|sqlite3)-(?:wal|shm|journal)$", name)
    ):
        raise AuditError(f"{path}: dato, modelo, base de datos o clave privada")
    if len(content) > MAX_BYTES:
        raise AuditError(f"{path}: excede el máximo de 1 MiB")
    if any(value in content for value in secrets):
        raise AuditError(f"{path}: coincide con un secreto del .env local")
    if any(pattern.search(content) for pattern in TOKEN_PATTERNS):
        raise AuditError(f"{path}: posible token o clave privada; no se muestra el valor")
    if path in DVC_POINTERS and not path_only:
        try:
            document = yaml.safe_load(content)
            if not isinstance(document, dict) or set(document) != {"outs"}:
                raise ValueError("estructura")
            if not isinstance(document["outs"], list) or len(document["outs"]) != 1:
                raise ValueError("outputs")
            out = document["outs"][0]
            if not isinstance(out, dict) or not (
                {"md5", "size", "path"} <= set(out) <= {"md5", "size", "path", "hash"}
            ):
                raise ValueError("campos")
            if not (
                re.fullmatch(r"[a-f0-9]{32}", out["md5"])
                and type(out["size"]) is int
                and out["size"] >= 0
                and out.get("hash", "md5") == "md5"
                and out["path"] == parts.name.removesuffix(".dvc")
            ):
                raise ValueError("contenido")
        except (ValueError, TypeError, KeyError, yaml.YAMLError, UnicodeError) as error:
            raise AuditError(f"{path}: puntero DVC inválido o contenido no permitido") from error
    if path == "data/original/.gitignore" and content:
        allowed = {f"/{name}.csv" for name in DVC_ORIGINALS | {"test", "sample_submission"}}
        if any(
            line.strip() and not line.lstrip().startswith("#") and line.strip() not in allowed
            for line in content.decode().splitlines()
        ):
            raise AuditError(f"{path}: exclusión local no reconocida")
    if name == ".env.example":
        for line in content.decode().splitlines():
            key, separator, value = line.partition("=")
            if (
                separator
                and not key.lstrip().startswith("#")
                and re.search(r"PASSWORD|SECRET|FERNET|TOKEN|PRIVATE|ACCESS_KEY", key)
                and value.strip()
            ):
                raise AuditError(f"{path}: la plantilla debe mantener los secretos vacíos")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def audit(mode, refs=()):
    root = Path(git("rev-parse", "--show-toplevel").decode().strip())
    secrets = private_values(root)
    entries = []
    commits = []
    if mode == "working-tree":
        paths = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
        for raw in paths:
            if not raw:
                continue
            path = raw.decode()
            actual = root / path
            validate_blob(
                path, b"", mode="120000" if actual.is_symlink() else "100644", path_only=True
            )
            if actual.stat().st_size > MAX_BYTES:
                raise AuditError(f"{path}: excede el máximo de 1 MiB")
            content = actual.read_bytes()
            validate_blob(path, content, secrets=secrets)
            entries.append((path, len(content)))
    else:
        trees = []
        if mode == "staged":
            trees = [git("ls-files", "--stage", "-z")]
        else:
            verified = [
                git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
                .decode()
                .strip()
                for ref in refs
            ]
            commits = git("rev-list", *verified).decode().splitlines()
            trees = [git("ls-tree", "-r", "-z", commit) for commit in commits]
        seen = set()
        for tree in trees:
            for entry in tree.split(b"\0"):
                if not entry:
                    continue
                metadata, raw_path = entry.split(b"\t", 1)
                path = raw_path.decode()
                bits = metadata.decode().split()
                file_mode, oid = (bits[0], bits[1]) if mode == "staged" else (bits[0], bits[2])
                if (path, oid) in seen:
                    continue
                seen.add((path, oid))
                validate_blob(path, b"", mode=file_mode, path_only=True)
                if int(git("cat-file", "-s", oid)) > MAX_BYTES:
                    raise AuditError(f"{path}: blob histórico excede 1 MiB")
                content = git("cat-file", "blob", oid)
                validate_blob(path, content, mode=file_mode, secrets=secrets)
                entries.append((path, len(content)))
    return {
        "mode": mode,
        "commits_scanned": len(commits),
        "blobs_scanned": len(entries),
        "total_bytes": sum(n for _, n in entries),
        "largest": sorted(entries, key=lambda pair: pair[1], reverse=True)[:5],
        "result": "passed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--working-tree", action="store_true")
    group.add_argument("--staged", action="store_true")
    group.add_argument("--refs", nargs="+")
    args = parser.parse_args()
    try:
        result = audit(
            "working-tree" if args.working_tree else "staged" if args.staged else "history",
            args.refs or [],
        )
    except AuditError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
