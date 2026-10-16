"""Prepare a separate disposable-campaign spy fixture; do not install or enable."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'work/candidates/spy-batch-test-mod-1375'
MOD = HERE / 'mod/llm_diplomacy_spy_batch_test'
TECH = ROOT / 'work/runtime/unpacked-1.37.5/base/common/technologies/dip.txt'
TECH_SHA = '1d934addb4e1140a09de14391fcbff554fa5feae0e28b5640d44a4ce3e3f867e'
CAPABILITIES = ('may_corrupt_officials', 'may_sabotage_reputation', 'may_sow_discontent',
                'may_slander_merchants', 'may_sabotage_recruitment')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def create(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    return dict(bytes=len(raw), sha256=digest(raw))


def main():
    with TECH.open('rb') as stream:
        original = stream.read(65537)
    if len(original) > 65536 or digest(original) != TECH_SHA:
        raise ValueError('Exact unpacked technology source changed')
    marker = b'\tmay_fabricate_claims = yes'
    if original.count(marker) != 1:
        raise ValueError('Unique tech0 insertion anchor changed')
    additions = b''.join(b'\n\t' + key.encode() + b' = yes' for key in CAPABILITIES)
    expanded = original.replace(marker, marker + additions, 1)
    if len(expanded) != len(original) + len(additions):
        raise ValueError('Technology overlay length')
    descriptor = 'name="LLM Diplomacy Spy Batch Test"\nsupported_version="1.37.*"\ntags={ "Utilities" }\n'
    modifiers = '''llmt_spy_batch_pool = {
    diplomats = 100
    spy_action_cost_modifier = -0.75
}
'''
    decision = '''# One explicit FRA-only setup for a disposable paused campaign.
country_decisions = {
    llmt_spy_batch_prepare = {
        potential = {
            tag = FRA
            NOT = { has_country_flag = llmt_spy_batch_prepared }
        }
        allow = {
            is_at_war = no
            ENG = { exists = yes }
            NAV = { exists = yes }
        }
        effect = {
            remove_country_modifier = llm_diplomacy_test_pool
            add_country_modifier = { name = llmt_spy_batch_pool duration = -1 }
            add_spy_network_in = { who = ENG value = 100 }
            vassalize = NAV
            set_country_flag = llmt_spy_batch_prepared
            log = "EU4LLM_TEST|spy_batch_fixture_v1|prepared"
        }
        ai_will_do = { factor = 0 }
    }
}
'''
    localisation = '''l_english:
 llmt_spy_batch_prepare_title:0 "Prepare LLM diplomacy batch test"
 llmt_spy_batch_prepare_desc:0 "Disposable test campaign: 100 extra diplomats, England spy network, reduced spy costs and Navarre vassal."
 llmt_spy_batch_pool:0 "LLM diplomacy batch test resources"
'''
    files = {
        'descriptor.mod': descriptor.encode(),
        'common/technologies/dip.txt': expanded,
        'common/defines/zz_llmt_spy_batch.lua': b'NDefines.NDiplomacy.DIPLOMAT_COOLDOWN_TIME = 0\n',
        'common/event_modifiers/llmt_spy_batch.txt': modifiers.encode(),
        'decisions/llmt_spy_batch.txt': decision.encode(),
        'localisation/llmt_spy_batch_l_english.yml': b'\xef\xbb\xbf' + localisation.encode(),
    }
    if HERE.exists():
        raise ValueError('CREATE_NEW candidate directory required')
    descriptors = {name: create(MOD / name, raw) for name, raw in files.items()}
    sources = {
        TECH.relative_to(ROOT).as_posix(): dict(bytes=len(original), sha256=TECH_SHA),
        Path(__file__).relative_to(ROOT).as_posix(): dict(bytes=Path(__file__).stat().st_size,
                                                        sha256=digest(Path(__file__).read_bytes())),
    }
    report = dict(schema_version=1, kind='prepared_spy_batch_test_mod', sources=sources,
                  mod_files=descriptors, technology_overlay='five capabilities inserted only in tech0',
                  decision='llmt_spy_batch_prepare', actor='FRA', spy_target='ENG', subject_target='NAV',
                  extra_diplomats=100, spy_network_add=100, spy_action_cost_modifier=-0.75,
                  stock_fees_milli=[25000, 60000, 80000, 70000, 80000],
                  theoretical_modified_total_milli=78750,
                  cooldown_define_months=0, decision_ai_factor=0, repeat_decision_guard=True,
                  installed=False, enabled=False, game_loaded=False, decision_executed=False,
                  raw_capabilities_verified=False, raw_spy_network_verified=False,
                  actual_fee_verified=False, actual_native_gate_verified=False,
                  individual_effect_verified=False, production_ready=False,
                  limits=['Only prepares separate mod files; no original mod, game files or load settings changed.',
                          'Technology overlay affects every country in this disposable test build.',
                          'Actual setup and total costs must be checked from held-process raw data before batch.',
                          'No scripted diplomacy substitutes for the five native actions being tested.'])
    encoded = (json.dumps(report, sort_keys=True, indent=2) + '\n').encode()
    create(HERE / 'report.json', encoded)
    print(json.dumps(dict(candidate=str(HERE.relative_to(ROOT)), report_sha256=digest(encoded),
                          mod_files=len(files), installed=False, game_access=False)))


if __name__ == '__main__':
    main()
