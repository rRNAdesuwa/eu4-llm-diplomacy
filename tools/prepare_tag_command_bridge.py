"""Copy the frozen native sender into a development host accepting arbitrary TAGs.

File-only: never opens the game or modifies a historical experiment.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "work/candidates/v29-gap-batch-1375"
OUT = ROOT / "bridge/native/tag_command_1375"


def pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def change(path, old, new, count=1):
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == count, (path, old, text.count(old))
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def main():
    index = json.loads((OLD / "source-index.json").read_bytes())
    OUT.mkdir(parents=True, exist_ok=False)
    origins = {}
    for name, expected in index.items():
        if name.startswith("src/") or name == "build_test.cmd":
            source = OLD / name
            assert pin(source) == expected, name
            target = OUT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            origins[source.relative_to(ROOT).as_posix()] = expected
    src = OUT / "src/work/candidates"
    host = src / "v26-gap-curry-bootstrap-1375"
    for path in [*host.iterdir(), OUT / "build_test.cmd"]:
        if path.is_file():
            data = path.read_text(encoding="utf-8")
            for old, new in [("pair29", "tagcommand30"), ("_v29", "_v30"),
                             ("restricted_pair_send_1375_v30", "tag_command_1375_v30"),
                             ("eu4_pair_send_lab_1375_v30", "eu4_tag_command_1375_v30"),
                             ("EU4PAIRSENDBOOT/1", "EU4TAGBOOT/1"),
                             ("EU4PAIRSEND/1", "EU4TAGCOMMAND/1")]:
                data = data.replace(old, new)
            path.write_text(data, encoding="utf-8", newline="\n")
    change(host / "codec.h", "||a>=Names.size()||(a<16)", "||a>=Names.size()")
    change(host / "test_codec.cpp", "if(action<16){assert(length<0);++groups;continue;} ", "")
    # Current human player is a stable world witness, not the action's actor.
    change(src / "v24-pair-send-core-r2-1375/pair_send.cpp",
           "s.current_player==s.actor && s.effective_player==s.actor",
           "valid(s.current_player) && country_slot(s.current_player)<s.count && s.effective_player==s.current_player")
    change(src / "v21-native-pair-guard-r3-1375/native_guard.cpp",
           "||z.current!=result.bindings[0].handle", "")
    env = src / "v21-native-pair-guard-r3-1375/native_env.cpp"
    change(env, "count<=122", "count<=0")
    change(env,
           "    if(!get(s.countries+122*8,s.actor_country)||!pointer(s.actor_country)||!get(s.countries+46*8,s.target_country)||!pointer(s.target_country)\n        )return false;",
           "    // Frame fields describe only the human player's unchanged context.\n"
           "    // The requested actor/target are resolved independently by NativePairGuard.\n"
           "    if(!get(s.game+0x1e60,s.player) || !(s.player>>56) || ((s.player>>48)&255)!=0)return false;\n"
           "    const auto player_slot=(s.player>>32)&65535;\n"
           "    if(player_slot>=f.countries_count || !get(s.countries+player_slot*8,s.actor_country) || !pointer(s.actor_country))return false;\n"
           "    s.target_country=s.actor_country;")
    change(env, "if(!get(s.actor_country+0x20,s.actor)||!get(s.target_country+0x20,s.target)",
           "if(!get(s.actor_country+0x20,s.actor)||s.actor!=s.player||!get(s.target_country+0x20,s.target)||s.target!=s.player")
    # Preserve factory-derived trust fields instead of assuming a particular Mod.
    # +40 = favor cost * 1000; +44 = trust gain. Historical V29 had these reversed.
    header = src / "v24-pair-send-port-r2-1375/native_pair_engine.h"
    change(header, "std::int32_t envoy{-1};\n};",
           "std::int32_t envoy{-1};std::int32_t trust_cost_milli{},trust_gain{};\n};")
    change(header, "std::int32_t envoy{-1};v21pair::OwnedId peer{},source{};",
           "std::int32_t envoy{-1},trust_cost_milli{},trust_gain{};v21pair::OwnedId peer{},source{};")
    engine = src / "v24-pair-send-port-r2-1375/native_pair_engine.cpp"
    change(engine,
           "if(e.profile->family==Family::FavorTrust && (get<std::int32_t>(e.address+0x40)!=5000 || get<std::int32_t>(e.address+0x44)!=1))fail(Fault::Fields);",
           "if(e.profile->family==Family::FavorTrust && (get<std::int32_t>(e.address+0x40)!=e.trust_cost_milli || get<std::int32_t>(e.address+0x44)!=e.trust_gain))fail(Fault::Fields);")
    change(engine, "auto& e=insert(result.object,f,Kind::Original);expected(e,true);return e.id;",
           "auto& e=insert(result.object,f,Kind::Original);\n"
           "    if(f.family==Family::FavorTrust) {\n"
           "        e.trust_cost_milli=get<std::int32_t>(e.address+0x40);e.trust_gain=get<std::int32_t>(e.address+0x44);\n"
           "        if(e.trust_cost_milli<0 || e.trust_cost_milli%1000 || e.trust_gain<=0 || e.trust_gain>100)fail(Fault::Fields);\n"
           "    }\n"
           "    expected(e,true);return e.id;")
    change(engine, "clone.source=cmd.id;", "clone.trust_cost_milli=e.trust_cost_milli;clone.trust_gain=e.trust_gain;clone.source=cmd.id;")
    change(engine, "clone.mode,clone.envoy};", "clone.mode,clone.envoy,clone.trust_cost_milli,clone.trust_gain};")
    submit = src / "v24-pair-send-port-r2-1375/submission_guard.cpp"
    change(submit, "s!=5000 || !at(e.clone,0x44,s) || s!=1",
           "s!=e.trust_cost_milli || !at(e.clone,0x44,s) || s!=e.trust_gain")
    # Record resolved handles so a receipt demonstrates whose action was queued.
    change(host / "bootstrap.cpp", " const auto result=job->core.invoke",
           " const auto& bound=job->guard.baseline();\n"
           " if(!record(\"pair_bound\",\",\\\"actor_handle\\\":%llu,\\\"target_handle\\\":%llu,\\\"human_player_handle\\\":%llu,\\\"actor_is_human_player\\\":%s\",\n"
           "  static_cast<unsigned long long>(bound.actor.value),static_cast<unsigned long long>(bound.target.value),\n"
           "  static_cast<unsigned long long>(bound.current_player.value),bound.actor==bound.current_player?\"true\":\"false\"))return;\n"
           " const auto result=job->core.invoke")
    # Add targeted offline guard tests to the native codec executable.
    change(host / "test_codec.cpp", " std::printf(\"codec_groups=",
           " {v21pair::PairStamp s{};s.process_creation=s.session=s.module_pin=s.owner_thread=s.world_witness=1;\n"
           "  s.database=0x10000;s.game=0x20000;s.array=0x30000;s.actor_object=0x40000;s.target_object=0x50000;s.count=200;s.date=1;\n"
           "  s.actor.value=0x0100000000000000ULL|(122ULL<<32)|0x415246;s.target.value=0x0100000000000000ULL|(46ULL<<32)|0x474e45;\n"
           "  s.current_player.value=0x0100000000000000ULL|(189ULL<<32)|0x524f50;s.effective_player=s.current_player;\n"
           "  assert(v21pair::valid(s));auto changed=s;changed.effective_player=s.actor;assert(!v21pair::valid(changed));\n"
           "  changed=s;changed.current_player=s.actor;changed.effective_player=s.actor;assert(!(s==changed));++groups;}\n"
           " std::printf(\"codec_groups=")
    (OUT / "origin-pins.json").write_text(json.dumps(origins, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"directory": str(OUT), "copied_sources": len(origins), "game_accessed": False}))


if __name__ == "__main__":
    main()
