"""Generate/check only the isolated v16 startup repair; never build/materialize."""
import argparse
import ast
import difflib
import hashlib
import json
import re
from candidate_guard import HERE, ROOT, writable, write

PREDECESSOR = "work/candidates/v15-acceptance-control-implementation-r3"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value,sort_keys=True,ensure_ascii=True,indent=2)+"\n").encode()


def bounded(path,maximum=8*1024*1024):
    if path.is_symlink() or path.is_junction():
        raise ValueError("Input must not be linked")
    with path.open("rb") as stream:
        raw=stream.read(maximum+1)
    if len(raw)>maximum:
        raise ValueError("Input exceeds bound")
    return raw


def frozen_inputs():
    pins=json.loads(bounded(HERE/"lineage.json"))
    for name,item in pins["files"].items():
        raw=bounded(ROOT/name)
        if digest(raw)!=item["sha256"] or len(raw)!=item["bytes"]:
            raise ValueError("Frozen lineage changed: "+name)
    original=json.loads(bounded(ROOT/"work/candidates/v15-acceptance-control-plan/input-pins.json"))
    for row in original["inputs"]:
        raw=bounded(ROOT/row["path"])
        if digest(raw)!=row["sha256"] or len(raw)!=row["bytes"]:
            raise ValueError("Frozen old input changed: "+row["path"])
    if len(original["inputs"])!=49:
        raise ValueError("Old frozen inventory differs")
    return original["inputs"],pins


def renamed(raw):
    return raw.decode().replace("\r\n","\n").replace("v15","v16").replace("V15","V16").replace("8771","8772")


def generate():
    frozen,pins=frozen_inputs()
    previous=json.loads(bounded(ROOT/PREDECESSOR/"candidate-index.json"))
    outputs={}
    source_by_target={}
    for name,item in previous["files"].items():
        raw=bounded(ROOT/name)
        if digest(raw)!=item["sha256"] or len(raw)!=item["bytes"]:
            raise ValueError("Materialized v15 source does not equal frozen candidate: "+name)
        target=name.replace("v15","v16")
        source_by_target[target]=name
        support=name in pins["support_sources"]
        fixture=name.startswith("work/candidates/fixture-v15-")
        outputs[target]=raw if support or fixture else renamed(raw).encode()
    header="work/native/v16/lab-request-1375.h"
    raw=outputs[header].decode()
    marker="inline bool same_binding(const AcceptanceWindow& w, const MailboxRequest& r) {"
    if raw.count(marker)!=1:
        raise ValueError("Expected unique startup insertion")
    outputs[header]=raw.replace(marker,bounded(HERE/"startup-window.inc").decode()+marker).encode()
    bootstrap="work/native/v16/research-lab-bootstrap-1375.inc"
    raw=outputs[bootstrap].decode()
    marker="    if (InterlockedCompareExchange(&installed, 1, 0)) return 10;\n"
    if raw.count(marker)!=1:
        raise ValueError("Expected unique one-shot BridgeStart CAS")
    outputs[bootstrap]=raw.replace(marker,marker+"    if (!eu4_lab_1375::initialize_startup_window(acceptance_window)) return 32;\n").encode()
    native={name:digest(raw).upper() for name,raw in outputs.items()
        if name.startswith("work/native/v16/") or name.startswith("work/native/test-fixture-v16-")}
    review=json.loads(bounded(ROOT/PREDECESSOR/"native-source-review.json"))
    review["purpose"]="v16_unbuilt_native_startup_contract"
    review["native_source_sha256"]=native
    review["startup_initialization"]={"pristine_closed_only":True,"canonical_names":"none",
        "position":"after_one_shot_install_CAS_before_hook_or_log","closed_history_cleared":False,
        "independent_mismatch_review_sha256":"5580e1dc1df3800fccca7b5f1c5b23efb0edcd6f6c672576b70ad9a7ed44fbc4",
        "stopped_failure_summary_sha256":"2d667210b7d9960ff614cdc8056038c8106014b63a4c918a5a7f21a667705d00"}
    review_raw=encoded(review)
    protocol="work/native/lab_protocol_v16_1375.py"
    raw=outputs[protocol].decode()
    constants={"EXPECTED_NATIVE_SOURCES":native,"NATIVE_REVIEW_SHA256":digest(review_raw),
        "NATIVE_REVIEW_PATH":"work/candidates/v16-acceptance-initialization-review/native-source-review.json"}
    for name,value in constants.items():
        raw,count=re.subn(r"^"+name+r" = .*$",name+" = "+repr(value),raw,flags=re.M)
        if count!=1:raise ValueError("Missing protocol constant: "+name)
    outputs[protocol]=raw.encode()
    if len(outputs)!=47 or len(native)!=22:
        raise ValueError("Source inventory differs")
    for name,raw in outputs.items():
        if name.endswith(".py"):ast.parse(raw.decode(),filename=name)
    artifacts={"native-source-review.json":review_raw}
    differences={}
    minimal=[]
    for target,source in source_by_target.items():
        before=bounded(ROOT/source)
        delta="".join(difflib.unified_diff(before.decode().splitlines(True),outputs[target].decode().splitlines(True),
            fromfile=source,tofile=target)).encode()
        if delta:
            name="diffs/"+target.replace("/","__")+".diff"
            artifacts[name]=delta;differences[name]=digest(delta)
        # Version-normalized semantic delta excludes expected constant pins.
        if target in (header,bootstrap):
            minimal.append("".join(difflib.unified_diff(renamed(before).splitlines(True),outputs[target].decode().splitlines(True),
                fromfile="version-renamed/"+target,tofile=target)))
    artifacts["startup-only.diff"]="".join(minimal).encode()
    artifacts["candidate-index.json"]=encoded({"schema_version":1,"purpose":"isolated_v16_unbuilt_startup_repair",
        "files":{name:{"sha256":digest(raw),"bytes":len(raw)} for name,raw in sorted(outputs.items())},
        "counts":{"native":22,"host":12,"support":8,"fixture":5,"total":47},
        "native_review_sha256":digest(review_raw),"diff_sha256":differences,"frozen_inputs_checked":len(frozen),
        "materialized":False,"native_built":False,"game_accessed":False,"production_backend_registered":False})
    return outputs,artifacts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--check",action="store_true")
    choice.add_argument("--refresh-candidate",action="store_true")
    args=parser.parse_args(argv)
    if args.refresh_candidate:writable()
    outputs,artifacts=generate()
    actual={}
    for path in (HERE/"files").rglob("*"):
        if "__pycache__" in path.parts:continue
        if path.is_symlink() or path.is_junction():raise ValueError("Linked output")
        if path.is_file():actual[path.relative_to(HERE/"files").as_posix()]=True
        if len(actual)>128:raise ValueError("Source inventory limit")
    if set(actual)-set(outputs):raise ValueError("Unexpected candidate output")
    for name,raw in {**{"files/"+name:raw for name,raw in outputs.items()},**artifacts}.items():
        if args.check:
            if not (HERE/name).is_file() or bounded(HERE/name)!=raw:raise ValueError("Candidate differs: "+name)
        else:write(HERE/name,raw)
    print(json.dumps({"checked":True,"proposed_sources":47,"materialized":False,"native_built":False,"game_accessed":False}))


if __name__=="__main__":main()
