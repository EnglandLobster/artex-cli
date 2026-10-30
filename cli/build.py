#!/usr/bin/env python3
"""Build a portable Python zipapp; no pip, Go, or Node dependency."""
import argparse
import pathlib
import tempfile
import shutil
import zipapp

root = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=pathlib.Path, default=root.parent / "dist/artexctl")
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    shutil.copytree(root / "artex_cli", pathlib.Path(tmp) / "artex_cli",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    zipapp.create_archive(tmp, args.output, interpreter="/usr/bin/env python3",
                          main="artex_cli.main:entrypoint", compressed=True)
args.output.chmod(0o755)
print(args.output)
