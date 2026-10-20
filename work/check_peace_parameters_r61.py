"""Exercise the production receipt formatter at maximum bounded field sizes."""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work.local_config import get_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    production = (ROOT / "work/native/peace-execution.inc").read_text(encoding="utf-8")
    functions = production[production.index("static bool execution_peace_subject_csv("):
                           production.index("static void execution_peace_emit_submission(")]
    source = r'''#include "peace-execution-wire.h"
#include <cstdio>
#include <cstring>
using PeaceExecutionRequest=bridge::peace_execution_wire::PeaceExecutionRequest;
''' + functions + r'''
int main() {
    PeaceExecutionRequest r{};
    strcpy(r.actor,"FRA"); strcpy(r.recipient,"ENG"); strcpy(r.direction,"demand");
    strcpy(r.war_id,"war_0123456789abcdef_01234567");
    r.demand_direction=true; r.amount_raw=2147483600;
    r.selected_amount=r.selected_provinces=r.selected_beneficiary=true;
    r.selected_reparations=r.selected_trade_power=r.selected_concede_defeat=true;
    r.selected_annul_treaties=r.selected_humiliate_rival=r.selected_show_strength=true;
    r.selected_force_religion=r.selected_return_core=r.selected_revoke_core=true;
    r.selected_release_subject=r.selected_transfer_subject=true;
    r.selected_release_nation=r.selected_force_vassalization=r.selected_form_personal_union=true;
    r.selected_grant_independence=r.selected_full_annexation=true;
    strcpy(r.term_mask,"mprtcahsfbvlx"); strcpy(r.country_term_mask,"mprtcahsfbvlxnzuie");
    strcpy(r.beneficiary,"FRA"); strcpy(r.trade_power_source,"ENG"); strcpy(r.trade_power_beneficiary,"FRA");
    strcpy(r.annul_country,"ENG"); strcpy(r.return_core_owner,"FRA"); strcpy(r.revoke_core_owner,"ENG");
    strcpy(r.release_nation_country,"FLY"); strcpy(r.release_nation_source,"ENG");
    strcpy(r.vassal_country,"LEI"); strcpy(r.vassal_beneficiary,"FRA");
    strcpy(r.union_country,"LEI"); strcpy(r.union_beneficiary,"FRA");
    strcpy(r.independence_country,"ENG"); strcpy(r.annex_country,"UTR"); strcpy(r.annex_beneficiary,"FRA");
    r.province_count=r.return_core_count=r.revoke_core_count=r.annul_partner_count=16;
    r.release_subject_count=r.transfer_subject_count=16;
    for (unsigned i=0;i<16;++i) {
        r.province_ids[i]=r.return_core_ids[i]=r.revoke_core_ids[i]=2147483647;
        snprintf(r.annul_partners[i],4,"A%02u",i);
        snprintf(r.release_subject_countries[i],4,"B%02u",i);
        snprintf(r.transfer_subject_countries[i],4,"C%02u",i);
    }
    char output[4096]{};
    execution_peace_parameters_json(r,output); printf("{%s}\n",output);
    r.selected_transfer_subject=false;
    execution_peace_parameters_json(r,output); printf("{%s}\n",output);
    r.selected_release_subject=false; r.selected_transfer_subject=true;
    execution_peace_parameters_json(r,output); printf("{%s}\n",output);
}
'''
    cpp, exe = out / "formatter.cpp", out / "formatter.exe"
    cpp.write_text(source, encoding="utf-8")
    command = [get_value("EU4_CXX"), "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
               "-I", str(ROOT / "work/native"), str(cpp), "-o", str(exe)]
    built = subprocess.run(command, capture_output=True, text=True, check=False)
    (out / "build.log").write_text(built.stdout + built.stderr, encoding="utf-8")
    if built.returncode:
        raise RuntimeError("FORMATTER_COMPILE_FAILED")
    completed = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    (out / "receipts.jsonl").write_text(completed.stdout, encoding="utf-8")
    rows = [json.loads(line) for line in completed.stdout.splitlines()]
    checks = {"three_complete_json_objects": len(rows) == 3,
              "full_mask_retained": rows[0]["term_mask"] == "mprtcahsfbvlxnzuie",
              "all_nine_country_tags_retained": all(key in rows[0] for key in (
                  "release_nation_country", "release_nation_source", "vassal_country", "union_country",
                  "independence_country", "annex_country", "vassal_beneficiary", "union_beneficiary", "annex_beneficiary")),
              "maximum_old_arrays_retained": all(len(rows[0][key]) == 16 for key in (
                  "province_ids", "return_core_ids", "revoke_core_ids", "annul_partners")),
              "single_release_omits_transfer": "transfer_subject_countries" not in rows[1],
              "single_transfer_omits_release": "release_subject_countries" not in rows[2]}
    report = {"status": "passed" if all(checks.values()) else "failed", "checks": checks,
              "fragment_bytes": [len(line.encode()) - 2 for line in completed.stdout.splitlines()],
              "capacity": 4096, "business_executed": False}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
