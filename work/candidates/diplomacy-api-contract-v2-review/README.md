# Public Contract/2 API integration candidate

This is a review-only patch, not an installation. All nine proposed files live under `files/`; the real `bridge/`, `tools/`, documentation, frozen v17 sources, manifests, DLLs and capability history remain unchanged. No backend, game process, request publisher, native callback or SQLite idempotence reservation is added to Contract/2.

`DiplomacyAPI.contract(version=2)` constructs the audited 274-action contract independently of the V1 `DiplomacyAPI.__init__`. Existing V1 methods, validator functions, catalog and request schema remain AST-identical. The two V1 parameters `region_id` and `rebel_faction_id` remain supported in V1. V2 explicitly requires `EU4DIPLOMACY-CONTRACT/2` and changes only those two schemas; the other 272 match V1. All requests remain unsupported drafts.

## Proposed files

| File | Delta |
| --- | --- |
| `bridge/diplomacy_api.py` | One static factory, before all unchanged V1 methods |
| `bridge/diplomacy_contract_v2.py` | Limited relocation of the already reviewed contract; APIError transport mapping and detached normalized draft parameters |
| `bridge/diplomacy_contract_v2_bindings.json` | Byte-identical audited 15-binding artifact |
| `bridge/diplomacy_contract_v2_pins.json` | Fixed evidence/catalog pins plus original contract/review lineage; removes self-referential pre-change API source pin |
| `bridge/diplomacy_service.py` | Four V2 routes, lazy contract creation, V2 16 KiB body limit, optional no-V1 service |
| `tools/diplomacy.py` | Explicit `--api-version 2` with only describe/validate/request; no implicit submit/preview aliases |
| `tools/serve_diplomacy.py` | Optional `--contract-only` avoids all V1 database/config/build initialization |
| `docs/diplomacy-api.md` | Appended V2 usage and limits; old documentation remains |
| `bridge/tests/test_diplomacy_contract_v2.py` | Offline public factory, CLI and real loopback HTTP integration tests |

HTTP: GET `/v2/actions`, GET `/v2/actions/{id}`, POST `/v2/validate`, POST `/v2/requests`. The last returns **501 with an intact usable draft**, including normalized `parameters`, canonical JSON/digest and explicit unsupported reason. There are no V2 status/audit/reconcile endpoints. `request_id` remains `not_reserved_contract_only`, even if the same identifier already exists in a V1 ledger. The default mixed service still initializes the existing V1 database as before; requests to V2 never use it. `--contract-only` constructs no V1 API at all.

The adopted contract no longer compiles the old API source from a pinned byte string, because the integration necessarily modifies that file and would otherwise create a self-hash problem. It imports the current package's unchanged `validate_value`, `REQUEST_ID` and `APIError` definitions. `prepare.py` asserts the whole old API AST, excluding the single new factory, is unchanged. Both original V1 test modules are replayed against the proposed modules. The remaining evidence is still checked one file at a time against fixed hash/size limits; no current process is inspected. A newly installed package must include these relative static evidence files, or V2 fails closed.

## Offline reproduction

From the repository root:

```powershell
python -B work/candidates/diplomacy-api-contract-v2-review/prepare.py --check
python -B work/candidates/diplomacy-api-contract-v2-review/test_bootstrap.py
```

The bootstrap copies only pinned inputs and generated outputs into a temporary tree, overlays the package paths, verifies all five loaded entry modules originate there, and runs the unchanged V1 API/reconciliation suites plus the new V2 suite. Unchanged support comes from the repository and is separately hashed in validation. Temporary SQLite files are used only by legacy V1 regression cases. V2 tests replace V1 construction, SQLite, subprocess and configuration access with failures. Local HTTP listeners and threads are shut down and joined; no game or native code is involved.

`validate.py --output <new-directory>` adds CreateNew captured stdout/stderr, exit codes and input hashes before/after. Do not reuse an existing output directory. The saved `validation-final` passed all 50 methods and `prepare --check`; 53 tracked files were unchanged. No formal files were applied or installed.

Development failures are retained: attempt 01 completed prepare-check but its recording harness used a relative output path with `relative_to(absolute ROOT)` and stopped before tests. Only the harness resolved the output path afterward. Attempt 02 exposed a temporary namespace package fixture missing the `bridge.tests` parent attribute, so three suite imports failed; only the bootstrap fixture was fixed. All generated implementation bytes were unchanged across these two repairs and the passing run. Original harnesses and outputs remain under their attempt directories.

## Review/application boundary

`candidate-index.json` pins 34 original inputs and all nine proposed outputs. `patch.diff` is the complete patch. The generator's input preimages are for pre-application review: it is expected to reject after a later authorized installation changes those original files. Application is not performed here; the root reviewer must first check preimages, then explicitly copy only the approved output paths and verify their new hashes. No deployment, registration, production readiness or actual diplomacy capability is claimed.

Call examples are in the appended documentation and `v2-documentation.md`. The candidate is sealed pending independent review; do not revise it in place after acceptance.
