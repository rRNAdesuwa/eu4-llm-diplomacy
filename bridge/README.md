# EU4LLM bridge

This directory contains the offline bridge tooling for the EU4 mod. It does
not automate the game window and it does not modify the mod or an EU4
installation. It parses protocol records from `game.log` and compiles a
strictly whitelisted JSON action request into a text file for the EU4
console's `run` command.

## Protocol

The game writes one complete snapshot as:

```text
EU4LLM|BEGIN|live|FRA
EU4LLM|FIELD|live|year|1444
EU4LLM|FIELD|live|treasury|250.00
EU4LLM|END|live
```

The snapshot ID is an identifier matching `[A-Za-z0-9_]{1,32}`. `FIELD`
keys match `[A-Za-z][A-Za-z0-9_]{0,31}` and values are retained as strings.
The parser accepts normal game-log prefixes before `EU4LLM|`, but validates
the protocol payload after that marker exactly. Only `FRA` snapshots are
accepted. Reusing `live` for later complete snapshots is supported.

Action receipts use the following exact format and statuses:

```text
EU4LLM|ACK|request_id|applied
EU4LLM|ACK|request_id|rejected
```

Strict parsing rejects a truncated snapshot, nested/interleaved `BEGIN`
records, mismatched IDs, fields outside a snapshot, duplicate field keys,
invalid identifiers, malformed records, and an ACK encountered while a
snapshot is open. `--lenient` is available for tailing a log: it drops the
invalid record and reports an `issues` array, so it must not be used to make
state-changing decisions.

## Commands

Run these commands from the repository root:

The Python command should use the project's configured environment. For the
Windows helper scripts, copy `local.env.example` to the ignored local file
`local.env` and set `EU4_PYTHON`; no machine-specific Python path is stored in
the repository.

```powershell
python -m bridge parse <game-log-path> --pretty
python -m bridge parse <game-log-path> --lenient --pretty
python -m bridge compile .\request.json .\run\llm_request.txt
python -m unittest discover -s bridge\tests -v
```

`parse` prints JSON with `snapshots` and `acks`. A strict parse error or an
invalid request exits with status 2. `compile` accepts either one object or a
non-empty JSON list. A request has this shape:

```json
{"id":"req_1","action":"lock_diplomacy"}
```

`request_id` may be used instead of `id`; if both are present they must be
identical. The only actions are:

```json
{"id":"snap_1","action":"snapshot"}
{"id":"req_1","action":"lock_diplomacy","target":"FRA"}
{"id":"req_2","action":"unlock_diplomacy","target":"FRA"}
{"id":"req_3","action":"improve_relations","target":"ENG"}
{"id":"war_1","action":"declare_war","target":"ENG"}
```

Targets are fixed to FRA for lock/unlock and ENG for relation improvement/war.
Unknown JSON fields, arbitrary action names, nested values, code fragments,
invalid IDs, and other targets are rejected before any run file is written.

## Generated run files

Every request is wrapped in a global `exists = FRA` check and then a FRA
country scope. The action branch checks `tag = FRA`, `ai = yes`, and
`exists = yes`. Mutating requests additionally require that
`llm_req_<id>` is absent, set that country flag on success, and emit an
`EU4LLM|ACK|<id>|applied` or `...|rejected` log line. Replaying the same
request therefore cannot apply it twice. `snapshot` is read-only and
repeatable; its exporter is inlined from the mod's fixed snapshot effect.

`lock_diplomacy` sets `llm_diplomacy_locked`; `unlock_diplomacy` clears it.
`improve_relations` remains available to the explicitly authorized bridge
while the native diplomacy lock is set. It verifies `ENG = { exists = yes }`
and emits only:

```text
add_opinion = {
    who = ENG
    modifier = llm_bridge_goodwill
}
```

The generated file is plain text. Copy it to the game's expected run-file
location and execute it through the normal EU4 console workflow appropriate
for the test installation.

`declare_war` uses the native script effect `declare_war_with_cb`, fixed to
FRA → ENG, `cb_core`, Maine (177). It requires locked, independent AI FRA,
both countries to exist, no FRA–ENG war/truce/alliance, a valid reconquest CB,
and an ENG-owned FRA core in 177. It never clears or resets the diplomacy
lock. Only confirmed `war_with = ENG` with the lock and AI still active emits
`applied` and marks the request used. Other outcomes emit `rejected`.
Caller-supplied CBs, provinces and other targets are rejected.

v9 的原生入口会在游戏帧中消费固定的 `declare-war.request`，执行正式
compiler 生成的 `llm_auto.txt`，再确认 ACK、法国 AI/锁快照和英法实际战争。
因此当前人工实验不需要手动运行战争测试文件；同一进程的宣战、实验战争分
和授权议和见 `work/automated-diplomacy-v9.md` 与
`docs/人工实验与日志读取流程.md`。

The Codex harness schema, decision validator and request mapping support this
same action. Its prompt requires an explicit player request for this reconquest;
the current snapshot cannot establish CB/truce/ownership prerequisites. The v9
DLL now performs the fixed in-process execution. `work/prepare_war_test.py`
and `work/prepare_war_diagnostic.py` remain available for script-layer tests and
read-only precondition probes.

Static reverse-engineering evidence remains in
`work/native-war-authorization-audit.md`; the v9 runtime result is in
`work/automated-diplomacy-v9.md`.

## Optional planning adapter

`bridge.planner.OpenAICompatiblePlanner` is a standard-library HTTP adapter
for an OpenAI-compatible `/v1/chat/completions` endpoint. It is disabled by
default. Enable it explicitly with `enabled=True` or
`EU4LLM_ENABLE_PLANNER=1`; configure `EU4LLM_OPENAI_ENDPOINT`,
`EU4LLM_OPENAI_MODEL`, and optionally `EU4LLM_API_KEY` in the process
environment. The adapter sends a snapshot, accepts one JSON action, and
passes the response through `ActionRequest` validation before returning it.
It does not persist the endpoint, API key, prompt, or response.
