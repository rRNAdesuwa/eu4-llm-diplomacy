"""Pinned file-only endpoint lookup; no target execution or process access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'work/candidates/war-peace-api-lookup-1375-v5/query_engine.py'
BASE_SHA = 'ea030ce19461b2e414e0cdbc42f4933551fa9e654f7a7a43db948670b27fa466'
DATA_SHA = '39efa19ba26675647379f6be182b26be727762d5eaf906f0be822b7ca0dba69c'
GAME_SHA = '9ad3efe1af169f40ee577f9dae5debbc87af6fb8b5450fb345ebf110dc4d771a'
FLAGS = ('callable', 'native_ready', 'sender_authorized',
         'gameplay_effect_verified', 'process_authenticated',
         'selected_effect_verified', 'world_lease', 'atomic_snapshot', 'authorizes_retry')


def base_bytes():
    with BASE.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if not 0 < len(raw) <= 1024 * 1024 or hashlib.sha256(raw).hexdigest() != BASE_SHA:
        raise ValueError('frozen_lookup_engine_changed')
    return raw


def engine():
    raw = base_bytes()
    module = types.ModuleType('_eu4_frozen_file_lookup_v1')
    module.__file__ = str(BASE)
    exec(compile(raw, str(BASE), 'exec'), module.__dict__)
    base_bytes()
    return module


def unknown(operation, reason):
    return dict(schema='EU4-WAR-PEACE-LOOKUP-RESULT/1', operation=operation,
        status='unknown', version='1.37.5', game_sha256=GAME_SHA,
        tool_revision=5, reason=reason, entries=[], count=0,
        identity_scope='retained_evidence_target_only_not_current_process_authentication',
        accounting_scope='this_offline_query_only', requests_published=0, native_calls=0,
        **{name: False for name in FLAGS})


def run(operation, selector=None, family=None, base=None, limit=20):
    """No graph/root/manifest override is exposed by this wrapper."""
    try:
        module = engine()
        graph = module.SourceGraph(ROOT, HERE, DATA_SHA)
        result, code = module.query(graph, operation, selector, family, base, limit)
        base_bytes()
        result.update(tool_revision=5, reused_engine_sha256=BASE_SHA,
                      original_engine_source_guard_before_and_after=True,
                      selected_effect_verified=False, world_lease=False,
                      atomic_snapshot=False, authorizes_retry=False)
        return result, code
    except (OSError, ValueError, KeyError, TypeError):
        return unknown(operation, 'fixed_lookup_sources_unavailable_or_changed'), 2


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('invalid_cli_arguments: ' + message)


def main(argv=None):
    parser = Parser(description='EU4 1.37.5 retained API evidence, revision 5; file queries only.')
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('check')
    catalog = commands.add_parser('catalog')
    catalog.add_argument('--family')
    search = commands.add_parser('search')
    search.add_argument('selector')
    search.add_argument('--family')
    search.add_argument('--limit', type=int, default=20)
    lookup = commands.add_parser('lookup')
    lookup.add_argument('selector')
    lookup.add_argument('--family')
    lookup.add_argument('--base')
    try:
        result, code = run(**vars(parser.parse_args(argv)))
    except ValueError:
        result, code = unknown('unknown', 'invalid_cli_arguments'), 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
