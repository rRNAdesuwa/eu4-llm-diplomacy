"""Candidate-only write guard; no formal materialization, build or game API."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def writable(here=HERE, root=ROOT):
    here, root = Path(here).resolve(), Path(root).resolve()
    if here == root or not here.is_relative_to(root):
        raise ValueError("Candidate must remain inside repository")
    for base in (root, here/"files"):
        runtime = base/"work/runtime/native1375-v17"
        if runtime.exists() and any(runtime.iterdir()):
            raise ValueError("Refuse regeneration after v17 build/session artifacts")
    for parent in (here, here/"files", here/"native-core"):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Candidate destination must not be a link")


def write(path, raw):
    writable()
    path = Path(path)
    if not path.resolve().is_relative_to(HERE) or path.is_symlink() or path.is_junction():
        raise ValueError("Only candidate-local files may be written")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == raw:
        return
    with path.open('xb') as stream: stream.write(raw)

