"""Contract/3 combines verified V2 descriptions with ten reviewed static shapes.

All requests are unsupported drafts. Source pins authenticate files only; this
module never authenticates a game process/world, resolves live handles, invokes
native code, opens SQLite or reserves a request identifier.
"""
from copy import deepcopy
from pathlib import Path

from .diplomacy_contract_v2 import (
    ContractCatalog as V2Catalog, digest, read_bounded, require, request_tree, strict_json,
)

HERE = Path(__file__).resolve().parent
PROTOCOL = 'EU4DIPLOMACY-CONTRACT/3'
PIN_SHA = '62219a79e2670ce3ff721bce9b9ba77fbf0059365dedc3857eb4265afebc46af'
TEN_ROOT = 'work/candidates/ten-families-typed-contract-r2-1375/'
TEN_CONTRACT = TEN_ROOT + 'contract.json'
TEN_INDEX = TEN_ROOT + 'source-index.json'
TEN_REPORT = TEN_ROOT + 'report.json'
TEN_REVIEW = TEN_ROOT + 'review.json'
INDEPENDENT_REVIEW = 'work/review-results/ten-families-r2-native-inventory-20261008a/review.json'
TEN_MIGRATIONS = ['sell_province', 'enforce_peace', 'threaten_war', 'trade_favors_for_trust']


class ContractCatalog(V2Catalog):
    def __init__(self, root=None):
        super().__init__(root)
        raw = read_bounded(HERE / 'diplomacy_contract_v3_pins.json', 64 * 1024)
        require(digest(raw) == PIN_SHA, 'V3 fixed source inventory changed', 'source_mismatch')
        self._v3_pins = strict_json(raw)
        require(type(self._v3_pins) is dict and len(self._v3_pins) == 6, 'V3 input inventory')
        retained = {}
        total = 0
        for name, pin in self._v3_pins.items():
            require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts,
                    'V3 nonrelative source path')
            path = (self.root / name).resolve()
            require(path.is_relative_to(self.root), 'V3 source escaped repository')
            require(type(pin) is dict and set(pin) == {'bytes', 'sha256'} and
                    type(pin['bytes']) is int and 0 <= pin['bytes'] <= 128 * 1024,
                    'V3 invalid source descriptor')
            source = read_bounded(path, pin['bytes'])
            total += len(source)
            require(total <= 512 * 1024, 'V3 source aggregate budget', 'input_budget')
            require(len(source) == pin['bytes'] and digest(source) == pin['sha256'],
                    'V3 reviewed source changed: ' + name, 'source_mismatch')
            if name in (TEN_CONTRACT, TEN_INDEX, TEN_REPORT, TEN_REVIEW, INDEPENDENT_REVIEW):
                retained[name] = strict_json(source)
        reviewed = retained[INDEPENDENT_REVIEW]['candidate_pins']
        for filename, path in (('contract.json', TEN_CONTRACT), ('source-index.json', TEN_INDEX),
                               ('report.json', TEN_REPORT), ('review.json', TEN_REVIEW)):
            require(reviewed[filename] == self._v3_pins[path]['sha256'], 'Reviewed candidate lineage differs')
        require(retained[TEN_INDEX]['sources']['contract.json'] == self._v3_pins[TEN_CONTRACT],
                'Ten-family contract/index lineage differs')
        require(retained[TEN_REPORT]['source_index_sha256'] == self._v3_pins[TEN_INDEX]['sha256'],
                'Ten-family report/index lineage differs')
        contract = retained[TEN_CONTRACT]
        require(contract['contract'] == 'TenFamiliesDraft/2' and len(contract['actions']) == 10,
                'Reviewed ten-family inventory differs')
        self._ten = contract['actions']
        require(set(self._ten) <= set(self._actions) and not set(self._ten) & set(self._bindings['actions']),
                'V2 and ten-family action inventory differs')
        self.verified_source_bytes += total
        # A reviewed static report is not runtime authorization. These values
        # are independent constants in every public readiness/request response.
        self._ten_blockers = [
            'Static parameter shape/source closure does not authenticate a live process/session/world.',
            'No live country/province/loaded-define binding or native legality was evaluated.',
            'Global observations, injected readers and cached extras are not runtime proof.',
            'No execution adapter, database, durable request reservation or native dispatch exists.',
        ]

    def _schema(self, action):
        if action in self._ten:
            return deepcopy(self._ten[action]['parameters'])
        return super()._schema(action)

    def _public_binding(self, action):
        fields = sorted(self._ten[action]['parameters']['properties'])
        result = {'kind': 'restricted_static_parameter_intent',
                  'public_fields': fields,
                  'parameter_binding_scope': 'restricted_static_parameter_shape_and_source_only',
                  'static_parameter_binding_closed': True,
                  'runtime_binding_verified': False, 'live_identity_resolved': False,
                  'native_legality': None, 'production_supported': False}
        if action == 'trade_favors_for_trust':
            result.update(kind='one_native_factory_step_intent',
                          quantity_source='two native loaded signed int32 define globals',
                          define_keys=['NDefines.NDiplomacy.INCREASE_TRUST_COST',
                                       'NDefines.NDiplomacy.INCREASE_TRUST_AMOUNT'],
                          cost_units='integer cost multiplied by 1000 in a supported signed32 encoding domain',
                          trust_units='integer trust points', current_values=None,
                          caller_quantity_override=False, stock_value_fallback=False,
                          cached_values_are_runtime_proof=False)
        elif action == 'reduce_relations_favor':
            result.update(kind='third_country_tag_intent',
                          selector='third_country ASCII country TAG',
                          resolution_requirement='authenticated current loaded country registry and private country resolver',
                          live_TAG_resolution_implemented=False,
                          normal_human_GUI_static_source_closed=True,
                          cached_selection_is_runtime_proof=False)
        elif action == 'sell_province':
            result.update(price_units='whole integer currency; bounded range is encoding syntax only')
        elif action == 'enforce_peace':
            result.update(opposing_country_role='opposing country TAG; private current-war relationship checks required')
        elif action == 'threaten_war':
            result.update(taker_constraint='taker_country must equal actor',
                          normal_full_preview_caller_closed=False)
        return result

    def describe(self, action=None):
        result = super().describe(action)
        result['protocol'] = PROTOCOL
        if action is None:
            result['typed_binding_extensions'] += len(self._ten)
            result['ten_family_static_parameter_bindings'] = len(self._ten)
            result['schema_migrations'] += TEN_MIGRATIONS
            for row in result['actions']:
                if row['action'] in self._ten:
                    row['typed_extension'] = True
            result['limits'].update(v3_source_count=6, v3_source_bytes=128 * 1024,
                                    v3_total_source_bytes=512 * 1024)
        elif action in self._ten:
            result['previous_v2_parameters'] = super()._schema(action)
            result['parameters'] = self._schema(action)
            result['parameter_validation'] = 'structural_and_restricted_cross_field_only'
            result['binding'] = self._public_binding(action)
            result['source_evidence'] = [{'path': path, **self._v3_pins[path]} for path in
                                         (TEN_CONTRACT, TEN_INDEX, INDEPENDENT_REVIEW)]
            result['readiness']['blockers'] = deepcopy(self._bindings['common_blockers']) + self._ten_blockers
        return result

    def validate(self, payload):
        encoded = request_tree(payload)
        payload = strict_json(encoded)
        require(type(payload) is dict and set(payload) == {'protocol', 'request_id', 'action', 'parameters'},
                'Request requires exactly protocol/request_id/action/parameters', 'invalid_request')
        require(payload['protocol'] == PROTOCOL, 'Explicit Contract/3 protocol required', 'protocol_version')
        require(type(payload['request_id']) is str and self._api.REQUEST_ID.fullmatch(payload['request_id']) is not None,
                'Invalid request_id', 'invalid_request')
        action = payload['action']
        self._entry(action)
        self._api.validate_value(payload['parameters'], self._schema(action))
        parameters = payload['parameters']
        if action in self._ten:
            require(parameters['actor'] != parameters['target'], 'Distinct actor/target required', 'invalid_parameters')
            if action == 'reduce_relations_favor':
                require(parameters['third_country'] not in (parameters['actor'], parameters['target']),
                        'Distinct third_country required', 'invalid_parameters')
            elif action == 'enforce_peace':
                require(parameters['opposing_country'] not in (parameters['actor'], parameters['target']),
                        'Distinct opposing_country required', 'invalid_parameters')
            elif action == 'threaten_war':
                require(parameters['taker_country'] == parameters['actor'],
                        'Explicit taker_country must equal actor', 'invalid_parameters')
        return {'schema_valid': True, 'protocol': PROTOCOL,
                'request_sha256': digest(encoded), 'canonical_request': encoded.decode('ascii'),
                'native_binding_resolved': False, 'runtime_binding_verified': False,
                'native_legality': None, 'production_supported': False}

    def _symbolic(self, action, parameters):
        if action not in self._ten:
            return super()._symbolic(action, parameters)
        result = self._public_binding(action)
        result.update(resolved=False, public_parameters=deepcopy(parameters))
        return result

    def request(self, payload):
        result = super().request(payload)
        result.update(protocol=PROTOCOL, runtime_binding_verified=False,
                      live_identity_resolved=False, execution_verified=False,
                      effect_verified=False, production_supported=False)
        return result
