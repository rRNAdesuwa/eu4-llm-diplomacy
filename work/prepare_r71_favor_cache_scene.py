"""Make the seeded LIT opinion entry and its serialized FRA cache consistent."""
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from work import prepare_r71_favor_inbound_ready as scene


def repair(lines):
    a, b = scene.child_span(lines, b"opinion_cache")
    cache = b"".join(lines[a:b])
    values = list(re.finditer(rb"-?\d+", cache))
    # This scene uses the checked 1.37.4 serialized country order:
    # LIT=97, FRA=122, PAP=206, SAV=210. FRA/PAP/SAV match live handles.
    slot = 97
    assert len(values) > 210
    match = values[slot]
    old = int(match[0])
    changed = cache[:match.start()] + b"200" + cache[match.end():]
    lines[a:b] = changed.splitlines(keepends=True)
    assert scene.scalar(lines, b"update_opinion_cache", b"yes") == 1
    c, d = scene.child_span(lines, b"active_relations")
    relations = lines[c:d]
    e, f = scene.child_span(relations, b"LIT")
    lithuania = relations[e:f]
    g, h = scene.child_span(lithuania, b"opinion")
    opinion = lithuania[g:h]
    assert b'"r35_test_vassal_opinion"' in b"".join(opinion)
    ending = b"\r\n" if opinion[0].endswith(b"\r\n") else b"\n"
    indent = re.match(rb"\s*", opinion[0])[0] + b"\t"
    for name, value in [(b"date", b"1456.1.2"), (b"expiry_date", b"yes")]:
        if scene.scalar(opinion, name, value) == 0:
            opinion.insert(1, indent + name + b"=" + value + ending)
    lithuania[g:h] = opinion
    relations[e:f] = lithuania
    lines[c:d] = relations
    return b"".join(lines), {"paths": ["countries/FRA/opinion_cache[97]",
        "countries/FRA/update_opinion_cache", "countries/FRA/active_relations/LIT/opinion"],
        "country": "LIT", "cache_slot": slot, "cache_before": old, "cache_after": 200,
        "treasury_or_favors_edited": False}


if __name__ == "__main__":
    scene.prepare_fra = repair
    scene.main()
