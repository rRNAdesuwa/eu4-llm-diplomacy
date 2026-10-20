"""Generate/check only the isolated v17 exact pin repair; never build/materialize."""
import argparse
import ast
import difflib
import hashlib
import json
import re
from candidate_guard import HERE, ROOT, writable, write
import pin_contract

PREDECESSOR = "work/candidates/v16-acceptance-initialization-review"


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


PORT_DEFAULTS = {
    "bridge/diplomacy_lab_http_v16.py": (
        'def make_server(service, *, host="127.0.0.1", port=8772, token):',
        'def make_server(service, *, host="127.0.0.1", port=8773, token):'),
    "tools/serve_diplomacy_lab_v16.py": (
        '    parser.add_argument("--port", type=int, default=8772)',
        '    parser.add_argument("--port", type=int, default=8773)'),
}

def renamed(raw, source=""):
    text = raw.decode().replace("\r\n","\n").replace("v16","v17").replace("V16","V17")
    # No numeric replacement in native sources, IDs, strings, or arbitrary URLs.
    # Only these two full frozen Python configuration lines contain the port.
    if source in PORT_DEFAULTS:
        before,after=PORT_DEFAULTS[source]
        if text.splitlines().count(before)!=1:raise ValueError("Exact port configuration line missing")
        text="\n".join(after if line==before else line for line in text.split("\n"))
    return text


def generate():
    frozen,pins=frozen_inputs()
    previous=json.loads(bounded(ROOT/PREDECESSOR/"candidate-index.json"))
    outputs={}
    source_by_target={}
    for name,item in previous["files"].items():
        raw=bounded(ROOT/name)
        if digest(raw)!=item["sha256"] or len(raw)!=item["bytes"]:
            raise ValueError("Materialized v16 source does not equal frozen candidate: "+name)
        target=name.replace("v16","v17")
        source_by_target[target]=name
        support=name in pins["support_sources"]
        fixture=name.startswith("work/candidates/fixture-v16-")
        outputs[target]=raw if support or fixture else renamed(raw,name).encode()
    implementation="work/native/v17/test-acceptance-1375.cpp"
    raw=outputs[implementation].decode()
    bad="483bd87720488d0419"
    good="483bd87710488d0419"
    if raw.count(bad)!=1 or good in raw:raise ValueError("Expected unique frozen pin typo")
    outputs[implementation]=raw.replace(bad,good).encode()
    pin_result=pin_contract.check(outputs[implementation].decode())
    native={name:digest(raw).upper() for name,raw in outputs.items()
        if name.startswith("work/native/v17/") or name.startswith("work/native/test-fixture-v17-")}
    review=json.loads(bounded(ROOT/PREDECESSOR/"native-source-review.json"))
    review["purpose"]="v17_unbuilt_native_exact_pin_contract"
    review["native_source_sha256"]=native
    review["exact_pin_repair"]={"diagnosis_sha256":"8177389f6f924eb8f5ee2e3130af717a1753ab1bc0d16dcd645cfa4faf17c5f5",
        "rva":"0xe50222","old_byte":"20","new_byte":"10","handler_bytes":648,
        "all_code_pins":8,"code_bytes":945,"guard_removed":False,"runtime_verified":False}
    review_raw=encoded(review)
    protocol="work/native/lab_protocol_v17_1375.py"
    raw=outputs[protocol].decode()
    constants={"EXPECTED_NATIVE_SOURCES":native,"NATIVE_REVIEW_SHA256":digest(review_raw),
        "NATIVE_REVIEW_PATH":"work/candidates/v17-acceptance-pin-review/native-source-review.json"}
    for name,value in constants.items():
        raw,count=re.subn(r"^"+name+r" = .*$",name+" = "+repr(value),raw,flags=re.M)
        if count!=1:raise ValueError("Missing protocol constant: "+name)
    outputs[protocol]=raw.encode()
    if len(outputs)!=47 or len(native)!=22:
        raise ValueError("Source inventory differs")
    for name,raw in outputs.items():
        if name.endswith(".py"):ast.parse(raw.decode(),filename=name)
    artifacts={"native-source-review.json":review_raw,"exact-pin-check.json":encoded(pin_result)}
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
        if target == implementation:
            minimal.append("".join(difflib.unified_diff(renamed(before,source).splitlines(True),outputs[target].decode().splitlines(True),
                fromfile="version-renamed/"+target,tofile=target)))
    artifacts["pin-only.diff"]="".join(minimal).encode()
    artifacts["candidate-index.json"]=encoded({"schema_version":1,"purpose":"isolated_v17_unbuilt_exact_pin_repair",
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
