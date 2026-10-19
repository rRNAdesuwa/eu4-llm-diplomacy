"""Verify the sealed finite candidate; never regenerate or promote it."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(path, limit):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Artifact exceeds fixed byte limit")
    return data


def load(name):
    spec = importlib.util.spec_from_file_location(f"typed_binding_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check():
    index = json.loads(read(HERE / "candidate-index.json", 128 * 1024))
    if index["schema_version"] != 1 or len(index["sources"]) > 64:
        raise ValueError("Unexpected candidate index")
    for rel, expected in index["sources"].items():
        path = (ROOT / rel).resolve()
        if not path.is_relative_to(ROOT) or type(expected["bytes"]) is not int or expected["bytes"] > 2 * 1024 * 1024:
            raise ValueError("Invalid source descriptor")
        data = read(path, expected["bytes"])
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"Pinned candidate source changed: {rel}")
    c = load("catalog")
    api = c.ContractCatalog()
    builder = load("build_artifacts")
    if json.loads(read(HERE / "bindings.json", 128 * 1024)) != builder.artifacts():
        raise ValueError("Bindings differ from finite source builder")
    discovery = api.describe()
    if (discovery["catalog_actions"], discovery["static_mapped"], discovery["typed_binding_extensions"]) != (274, 270, 15):
        raise ValueError("Coverage changed")
    return {"check": "passed", "source_count": len(index["sources"]),
            "source_bytes": api.verified_source_bytes, "catalog_actions": 274,
            "typed_binding_extensions": 15, "production_executable_actions": 0,
            "process_accessed": False, "native_called": False, "request_written": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(check(), sort_keys=True))
