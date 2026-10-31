"""Recupera desde storage en un clon aislado, sin borrar originales ni caché."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("train", "stores", "holidays_events", "oil", "transactions")


def fingerprint(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}


def source_state():
    return {n: fingerprint(ROOT / "data/original" / f"{n}.csv") for n in NAMES}


def cache_state():
    cache = ROOT / ".dvc/cache"
    return {str(p.relative_to(cache)): fingerprint(p) for p in cache.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--remote", default="storage")
    args = parser.parse_args()
    original, cached = source_state(), cache_state()
    revision = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{args.revision}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    for name in NAMES:
        subprocess.run(
            ["git", "cat-file", "-e", f"{revision}:data/original/{name}.csv.dvc"],
            cwd=ROOT,
            check=True,
        )
    temporary = Path(tempfile.mkdtemp(prefix="lab1-dvc-recovery-"))
    clone = temporary / "repo"
    subprocess.run(
        ["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(clone)], check=True
    )
    subprocess.run(["git", "-C", str(clone), "checkout", "--detach", revision], check=True)
    cache = clone / ".dvc/cache"
    if cache.exists() and any(p.is_file() for p in cache.rglob("*")):
        raise RuntimeError("El clon no comenzó con caché vacía")
    if list((clone / "data/original").glob("*.csv")):
        raise RuntimeError("El clon ya contiene CSV; no se probaría una recuperación real")
    env = {
        **os.environ,
        "DVC_NO_ANALYTICS": "true",
        "DVC_SITE_CACHE_DIR": str(temporary / "site-cache"),
    }
    subprocess.run(
        [sys.executable, "-m", "dvc", "pull", "-r", args.remote], cwd=clone, env=env, check=True
    )
    restored = {}
    for name in NAMES:
        p = clone / "data/original" / f"{name}.csv"
        restored[name] = fingerprint(p)
        if (
            restored[name]["sha256"] != original[name]["sha256"]
            or restored[name]["bytes"] != original[name]["bytes"]
        ):
            raise RuntimeError(f"Recuperación distinta del original: {name}")
    if len(list((clone / "data/original").glob("*.csv"))) != 5:
        raise RuntimeError("Se recuperaron archivos fuera de los cinco requeridos")
    if original != source_state() or cached != cache_state():
        raise RuntimeError("Se alteraron originales o caché principal")
    report = {
        "dvc_version": importlib.metadata.version("dvc"),
        "revision": revision,
        "remote": args.remote,
        "recovery_repo": str(clone),
        "clean_cache_before": True,
        "restored_files": restored,
        "total_bytes": sum(r["bytes"] for r in restored.values()),
        "originals_unchanged": True,
        "source_cache_unchanged": True,
    }
    target = ROOT / "data/dvc_recovery_report.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("El clon de verificación se conserva para inspección; no se eliminó ninguna caché.")


if __name__ == "__main__":
    main()
