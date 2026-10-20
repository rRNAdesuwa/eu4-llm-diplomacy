"""Read-only discovery of compiled TAG bindings and explicitly excluded labels."""
from bridge.tag_action_conditions import load_condition_document
from bridge.tag_command_backend import ROOT, decode, digest, read, require


def references(backend):
    document = load_condition_document(backend)
    raw = read(ROOT/'bridge/diplomacy_catalog.json', 4*1024*1024)
    require(digest(raw) == document['source_pins']['native_catalog']['bridge/diplomacy_catalog.json']['sha256'],
            'Lookup catalog changed during read')
    catalog = decode(raw)
    entries = {entry['action_id']:entry for entry in catalog['actions']}
    bindings = {entry['action']:entry for entry in backend.bindings}
    excluded = {entry['action']:entry for entry in backend.excluded}
    require(not bindings.keys() & excluded.keys(), 'Conflicting binding and exclusion')
    scope = bindings.keys() | excluded.keys()
    require(scope == {e['action_id'] for e in catalog['actions']
                      if e['category'] in backend.categories}, 'Lookup scope differs from registry')
    rows = {}
    for action in sorted(scope):
        binding = bindings.get(action)
        entry = entries[action]
        rows[action] = dict(action=action, name_en=entry['name_en'],
            category=entry['category'], support='bound' if binding else 'excluded',
            native_family=binding['native_family'] if binding else None,
            mode=binding['mode'] if binding else None,
            script_key=binding['script_key'] if binding else None,
            route=binding.get('route','pair_action') if binding else None,
            exclusion_reason=None if binding else excluded[action]['reason'],
            lookup_endpoint='/native/v1/actions/'+action)
    return document, entries, bindings, rows


def lookup_action(backend, action):
    document, entries, bindings, rows = references(backend)
    require(type(action) is str and action in rows, 'Unknown action in TAG lookup scope')
    record = document['actions'].get(action)
    return dict(rows[action], game_sha256=document['game_sha256'],
        native_manifest_sha256=backend.manifest_sha,
        evaluated_in_game=False, native_logic_complete=False,
        current_host_binding=bindings.get(action),
        native_check=record['native_check'] if record else None,
        catalog_native_mapping=entries[action].get('native_mapping'),
        catalog_unresolved=entries[action].get('native_unresolved',[]),
        native_research_findings=[f for f in document['native_research_findings'] if action in f['actions']],
        conditions_endpoint='/native/v1/conditions/'+action if record else None,
        limitations=[
            'Bound means compiled into this host, not current legality, acceptance or proven effect.',
            'Excluded records are research references; publishing them remains refused.',
            'RVA locations are file research evidence, never accepted as command inputs.',
            'Missing mapping or findings means unknown within this search, not absent in the executable.',
            'Catalog static variants and current compiled profile have separate provenance.'
        ], source_pins=document['source_pins'])


def search_actions(backend, *, query='', category=None, support=None, offset=0, limit=20):
    require(type(query) is str and len(query) <= 120, 'Search query must be at most 120 characters')
    require(category is None or category in backend.categories, 'Unknown action category')
    require(support is None or support in ('bound','excluded'), 'Support must be bound or excluded')
    require(type(offset) is int and 0 <= offset <= 147 and type(limit) is int and 1 <= limit <= 50,
            'Search page bounds: offset 0..147, limit 1..50')
    document, _, _, rows = references(backend)
    words = query.casefold().split()
    selected = []
    for row in rows.values():
        if category is not None and row['category'] != category:
            continue
        if support is not None and row['support'] != support:
            continue
        text = ' '.join(str(row[k] or '') for k in
                        ('action','name_en','category','native_family','script_key','exclusion_reason')).casefold()
        if all(word in text for word in words):
            selected.append(row)
    selected.sort(key=lambda row:(row['action'] != query.strip().casefold(),row['action']))
    end = min(len(selected),offset+limit)
    return dict(query=query, category=category, support=support, total=len(selected),
        offset=offset, limit=limit, next_offset=end if end < len(selected) else None,
        results=selected[offset:end], game_sha256=document['game_sha256'],
        evaluated_in_game=False, native_logic_complete=False,
        scope='147 TAG catalog labels: 120 compiled bindings and 27 exclusions',
        searched_fields=['action','name_en','category','native_family','script_key','exclusion_reason'],
        binding_does_not_prove_game_effect=True)
