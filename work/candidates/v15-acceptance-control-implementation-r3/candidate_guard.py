"""Candidate-only write guard. No materialization/build/process API is provided."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def writable(here=HERE, root=ROOT):
    here, root = Path(here).resolve(), Path(root).resolve()
    if here == root or not here.is_relative_to(root):
        raise ValueError("Candidate must remain inside the repository")
    for base in (root, here / "files"):
        runtime = base / "work/runtime/native1375-v15"
        if runtime.exists() and any(runtime.iterdir()):
            raise ValueError("Refuse regeneration after any v15 runtime/build/session artifact exists")
    # Files under files/ are source proposals, never a symlink into live output.
    for parent in (here, here / "files", here / "native-core"):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Candidate destination must not be a link/junction")


def write(path, data):
    writable()
    path = Path(path)
    resolved = path.resolve()
    if not resolved.is_relative_to(HERE) or path.is_symlink() or path.is_junction():
        raise ValueError("Only candidate-local ordinary files may be written")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)
