"""CreateNew frozen lineage/test copies for this candidate directory only."""
import hashlib
import json
from pathlib import Path
from candidate_guard import HERE,ROOT,writable

OLD="work/candidates/v15-acceptance-control-implementation-r3"


def raw(path):
    with path.open("rb") as stream:
        data=stream.read(8*1024*1024+1)
    if len(data)>8*1024*1024:raise ValueError("Oversized lineage")
    return data


def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as stream:stream.write(data)


def main():
    writable()
    files={}
    def pin(name,expected=None):
        data=raw(ROOT/name);h=hashlib.sha256(data).hexdigest()
        if expected and h!=expected:raise ValueError("Fixed input changed: "+name)
        files[name]={"bytes":len(data),"sha256":h}
        return data
    for path in sorted((ROOT/OLD).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:pin(path.relative_to(ROOT).as_posix())
    index=json.loads(pin(OLD+"/candidate-index.json","a03d61317818c7394c2b084dfeab455b61fe607b6ea8ec7cd1894c304db9495c"))
    manifest=json.loads(pin("work/runtime/native1375-v15/build.json","25aa20aaf3624cb25bd640d02407997388707f5ac29fc1f47954eb0809d47c2e"))
    for name,item in index["files"].items():
        data=pin(name,item["sha256"])
        assert len(data)==item["bytes"]
    pin("work/runtime/native1375-v15/eu4_pair_lab_v15_1375.dll",manifest["dll_sha256"].lower())
    for name,h in (
        ("work/review-results/v15-r3-external-api-20261008a/review.json","015bb0b2592fcacb23d732abf0973e8b5babe963506a99f34074ca1c5799675a"),
        ("work/review-results/v15-window-default-native-inventory-20261008a/review.json","5580e1dc1df3800fccca7b5f1c5b23efb0edcd6f6c672576b70ad9a7ed44fbc4"),
        ("work/review-results/v15-window-default-native-inventory-20261008a/report.json","748a50de64eb5fc2c98ffd71273543229c2ecdea90b307dac2bd036b104825bb"),
        ("work/runtime/native1375-v15/initial-closed-failure-summary-65368.json","2d667210b7d9960ff614cdc8056038c8106014b63a4c918a5a7f21a667705d00")):
        pin(name,h)
    for path in (ROOT/"work/review-results/v15-window-default-native-inventory-20261008a").iterdir():
        if path.is_file():pin(path.relative_to(ROOT).as_posix())
    failure=json.loads(raw(ROOT/"work/runtime/native1375-v15/initial-closed-failure-summary-65368.json"))
    for item in failure["input_artifacts"].values():pin(item["path"],item["sha256"])
    result={"schema_version":1,"predecessor":OLD,"files":files,
        "support_sources":list(manifest["support_source_sha256"]),"native_built":False,
        "materialized":False,"game_accessed":False,"production_ready":False}
    put(HERE/"lineage.json",(json.dumps(result,sort_keys=True,indent=2)+"\n").encode())
    for path in (ROOT/OLD).glob("test_*"):
        if path.is_file():
            put(HERE/path.name,raw(path).decode().replace("v15","v16").replace("V15","V16").replace("8771","8772").encode())
    for name in ("test-acceptance-1375.h","test-acceptance-1375.cpp"):
        put(HERE/"native-core"/name,raw(ROOT/OLD/"native-core"/name))
    print(json.dumps({"lineage_files":len(files),"game_accessed":False,"materialized":False}))


if __name__=="__main__":main()
