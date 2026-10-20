"""Bounded disk-only evidence for the v9 fixed NAV baseline guard."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/"work"))
sys.path.insert(0,str(Path(tempfile.gettempdir())/"eu4-native-analysis-deps"))
from discover_diplomacy import PE,check_memory_budget
from capstone import Cs,CS_ARCH_X86,CS_MODE_64

SHA="9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a"
RANGES=[
    ("alliance_index_getter",0xa68d90,0xa68dcb),
    ("overlord_handle_and_validity",0x2f1657,0x2f16e0),
    ("truce_mask_update",0xa6763d,0xa67689),
    ("vassal_cancel_mask_initialization",0x51f020,0x51f0a3),
    ("vassal_cancel_relation_truce_check",0x51f324,0x51f3e0),
]
ANCHORS={
    0xa68d9c:"488b8a80000000",0xa68da3:"4c63828c000000",0xa68dba:"4883c110",0xa68dc6:"488b4108",
    0x2f1657:"488b81f0180000",0x2f16cf:"48c1e938",0x2f16d8:"84c9",
    0xa67652:"440fb64645",0xa6765f:"4180c801",0xa67670:"4180e0fe",0xa67681:"44884645",
    0x51f04a:"b301",0x51f3a1:"0fb64745",0x51f3a5:"22c3",
}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--check",action="store_true");args=ap.parse_args()
    pe=PE(ROOT.parent/"eu4.exe");check_memory_budget()
    if hashlib.sha256(pe.data).hexdigest()!=SHA:raise ValueError("Wrong exact executable")
    md=Cs(CS_ARCH_X86,CS_MODE_64);blocks=[]
    for label,begin,end in RANGES:
        raw=pe.bytes_at(begin,end-begin)
        instructions=[{"rva":hex(i.address-pe.base),"bytes":i.bytes.hex(),"mnemonic":i.mnemonic,"op_str":i.op_str}
                      for i in md.disasm(raw,pe.base+begin)]
        if sum(len(bytes.fromhex(i["bytes"])) for i in instructions)!=len(raw):raise ValueError("Incomplete bounded decode")
        blocks.append({"name":label,"begin_rva":hex(begin),"end_rva_exclusive":hex(end),"byte_count":len(raw),
                       "sha256":hashlib.sha256(raw).hexdigest(),"instructions":instructions})
    for rva,expected in ANCHORS.items():
        if pe.bytes_at(rva,len(expected)//2).hex()!=expected:raise ValueError("Static anchor changed")
    report={"schema":"native_fixture_baseline_guard_1375_v1","runtime_verified":False,"exe_sha256":SHA,
        "scope":"fixed fixture_on FRA/NAV only; read-only fields, no method calls",
        "decoded_bytes":sum(b[2]-b[1] for b in RANGES),"blocks":blocks,
        "anchors":{hex(k):v for k,v in ANCHORS.items()},
        "fields":{"country_overlord":{"offset":"0x18f0","width":8,"valid_when":"high byte nonzero"},
                  "relation_counterpart":{"offset":"0x10","width":8,"full_handle_required":True},
                  "active_truce":{"record_offset":"0x45","width":1,"mask":1,"zero_based_bit":0},
                  "alliance_index":{"root_pointer_offset":"0x80","count_offset":"0x8c","count_width":4,
                                    "entry_size":16,"slot_offset":0,"object_pointer_offset":8}},
        "implementation_bounds":{"maximum_index_count":4096,"maximum_slot_exclusive":4096,"object_dereferences":False},
        "double_pass":"Both passes require clean pair; compare NAV pointer/overlord and bilateral record/root/index pointers, index counts and full truce flag bytes. Unrelated index entry order/identity is not compared.",
        "limitations":["Does not prove loaded save filename, complete world state, strict single-player origin or future script effects.",
                        "Absence of this known alliance-removal truce path is not proof that all fixture effects avoid truce.",
                        "Caller still verifies NAV exists in the intended independently audited baseline.",
                        "No runtime call or game-process read performed by this generator."]}
    payload=(json.dumps(report,indent=2)+"\n").encode();out=HERE/"baseline-guard-evidence.json"
    if args.check:
        if out.read_bytes()!=payload:raise ValueError("Evidence report differs")
    else:out.write_bytes(payload)
    check_memory_budget()
    print(json.dumps({"decoded_bytes":report["decoded_bytes"],"sha256":hashlib.sha256(payload).hexdigest(),"check":args.check}))

if __name__=="__main__":main()
