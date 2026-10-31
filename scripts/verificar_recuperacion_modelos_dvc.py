"""Recupera solo los 16 pesos actuales en caché aislada; nunca carga ni entrena modelos."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path):
    with path.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": sha256, "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns}


def files_state(root):
    return {str(p.relative_to(root)): fingerprint(p) for p in root.rglob("*") if p.is_file()}


def expected_paths():
    return {
        f"{model}/fold_{fold}/{filename}"
        for model in ("random_forest", "hist_gradient_boosting", "catboost")
        for fold in range(1, 5)
        for filename in (
            ("model.joblib", "model.cbm") if model == "catboost" else ("model.joblib",)
        )
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="storage")
    args = parser.parse_args()
    models = ROOT / "models/current"
    before = files_state(models)
    cached = files_state(ROOT / ".dvc/cache")
    if set(before) != expected_paths():
        raise ValueError("El conjunto no contiene exactamente los 16 archivos autorizados")
    temporary = Path(tempfile.mkdtemp(prefix="lab1-dvc-models-recovery-"))
    clone = temporary / "repo"
    subprocess.run(["git", "clone", "--no-hardlinks", str(ROOT), str(clone)], check=True)
    (clone / "models").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "models/current.dvc", clone / "models/current.dvc")
    shutil.copy2(ROOT / ".gitignore", clone / ".gitignore")
    if files_state(clone / ".dvc/cache") or (clone / "models/current").exists():
        raise RuntimeError("La recuperación debe iniciar sin pesos ni caché")
    env = {
        **os.environ,
        "DVC_NO_ANALYTICS": "true",
        "DVC_SITE_CACHE_DIR": str(temporary / "site-cache"),
    }
    subprocess.run(
        [
            sys.executable,
            "-m",
            "dvc",
            "config",
            "--local",
            "core.site_cache_dir",
            str(temporary / "site-cache"),
        ],
        cwd=clone,
        env=env,
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "dvc", "pull", "models/current.dvc", "-r", args.remote],
        cwd=clone,
        env=env,
        check=True,
    )
    restored = files_state(clone / "models/current")
    if set(restored) != expected_paths():
        raise RuntimeError("El remoto recuperó archivos fuera del conjunto autorizado")
    for relative, state in before.items():
        if any(restored[relative][key] != state[key] for key in ("sha256", "bytes")):
            raise RuntimeError(f"Recuperación distinta: {relative}")
    if before != files_state(models) or cached != files_state(ROOT / ".dvc/cache"):
        raise RuntimeError("Se alteraron los modelos locales o la caché principal")
    report = {
        "remote": args.remote,
        "recovery_repo": str(clone),
        "files": restored,
        "file_count": len(restored),
        "bytes": sum(v["bytes"] for v in restored.values()),
        "clean_cache_before": True,
        "source_models_unchanged": True,
        "source_cache_unchanged": True,
    }
    output = ROOT / "reports/dvc_models/recovery.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))


if __name__ == "__main__":
    main()
