# EU4 1.37.4 script audit (working notes)

Audit source: `EU4_GAME_ROOT`.

## Confirmed export syntax / fields

Vanilla exports country values with the legacy form:

```txt
export_to_variable = { which = money_available value = treasury who = ROOT }
export_to_variable = { which = our_manpower value = manpower who = ROOT }
export_to_variable = { which = their_manpower value = manpower who = FROM }
```

These are exact examples in `events/ConsortEvents.txt:1757,1778,1782`. The same file exports `max_manpower` and uses the same `which/value/who` shape. A newer variable-arithmetic context also uses:

```txt
export_to_variable = {
    variable_name = ai_value
    value = stability
    who = FROM
    with = ROOT
}
```

This is exact at `common/new_diplomatic_actions/00_diplomatic_actions.txt:347-354`. Therefore use `which = <name>` for ordinary effects/events; `variable_name = <name>` is proven inside the newer `variable_arithmetic_trigger`/AI arithmetic blocks. `value = treasury`, `value = manpower`, `value = stability`, and `value = max_manpower` are proven tokens. A boolean `is_at_war` is a trigger (`is_at_war = yes/no`), not a numeric export value in the vanilla examples searched; snapshot war status as a branch/flag or numeric constant.

## Immediate parent-facing minimum

For a FRA snapshot effect, the proven numeric exports are:

```txt
export_to_variable = { which = llm_snapshot_treasury value = treasury }
export_to_variable = { which = llm_snapshot_manpower value = manpower }
export_to_variable = { which = llm_snapshot_stability value = stability }
```

If an explicit `who` is needed, vanilla uses `who = ROOT` when the event scope may be elsewhere. For a country-scoped event on FRA, omitting `who` exports the current country value (the `flavorAJU.txt` example exports `treasury` with no `who` inside a country scope).

The requested log protocol can use literal messages around these exports:

```txt
log = "BEGIN|live|FRA"
export_to_variable = { which = llm_snapshot_treasury value = treasury }
export_to_variable = { which = llm_snapshot_manpower value = manpower }
export_to_variable = { which = llm_snapshot_stability value = stability }
log = "FRA|live|treasury|[Root.llm_snapshot_treasury.GetValue]"
log = "FRA|live|manpower|[Root.llm_snapshot_manpower.GetValue]"
log = "FRA|live|stability|[Root.llm_snapshot_stability.GetValue]"
if = {
    limit = { is_at_war = yes }
    log = "FRA|live|war|1"
}
else = { log = "FRA|live|war|0" }
log = "END|live"
```

Vanilla proves the `log = "..."` effect and bracketed text interpolation for scope getters: `events/center_of_revolution_events.txt:379,706` logs `[Root.GetName]` and `[GetYear]`; `events/disaster_Revolution.txt:20` logs `[Root.GetName]`. No vanilla `log` line searched contained `.GetValue`, so dynamic numeric interpolation in a log line is plausible from the shared text parser but remains a live-run check. `is_at_war` branch is proven trigger syntax throughout vanilla, but no vanilla numeric `export_to_variable` of that boolean was found.

## Numeric variable localisation

Vanilla localisation displays an exported variable using the scoped getter form, for example `localisation/emperor_content_l_english.yml:3374` uses `[1.GPW_counting_variable.GetValue]`, and `localisation/origins_l_english.yml:254,268` uses `[Root.mal_money_to_give_tt.GetValue]` and `[Root.trade_income_variable_tt.GetValue]`. For a local country variable, use `[Root.<variable_name>.GetValue]` in a country/event text context (or the scope prefix appropriate to the current text).

## Monthly on_action

Vanilla `common/on_actions/00_on_actions.txt:2046` defines an empty `on_monthly_pulse = { }`; nearby `on_yearly_pulse` is an `events = { ... }` list. The file therefore proves the key and its monthly cadence hook, but not a particular mod merge strategy. An appended `on_monthly_pulse = { events = { <event> } }` is the conventional shape to test in the mod; preserve the full vanilla diplomatic-actions file if modifying action definitions, as the parent requested.

## Opinion modifier and AI scope

Vanilla action effects use:

```txt
FROM = {
    add_opinion = {
        who = ROOT
        modifier = trade_protectorate_called_into_war
    }
}
```

Exact `common/new_diplomatic_actions/00_diplomatic_actions.txt:1624-1628`; the modifier is defined at `common/opinion_modifiers/00_opinion_modifiers.txt:5240` as an object with `opinion`, decay, and optional bounds. Thus `modifier = llm_bridge_goodwill` is valid only after the mod defines `llm_bridge_goodwill = { opinion = ... }` under `common/opinion_modifiers/`.

The action header says triggers/effects run in Actor scope and Recipient is `FROM` (`00_diplomatic_actions.txt:1`). Existing actions use `ai_will_do = { ... }` as a trigger, e.g. lines 362-378, with ordinary triggers and `FROM = { ... }` for recipient conditions. A scope-safe AI guard for an actor/recipient relation is therefore:

```txt
ai_will_do = {
    NOT = { has_country_flag = llm_diplomacy_locked }
    FROM = { NOT = { has_country_flag = llm_diplomacy_locked } }
}
```

Whether the lock should apply to both actor and recipient is a design choice; the syntax and scope are proven. `ai_will_do` is a trigger block, not an effect.

## Merge/override caveat

The older `common/diplomatic_actions/00_diplomatic_actions.txt` has explicit instructions at lines 2-14: an action can have any number of `condition` blocks, and each condition has its own `tooltip`, `potential`, and `allow`; `potential` determines whether that condition applies and `allow` determines whether the action is valid. `declarewar` lines 121-157 contains multiple live condition blocks, proving the structure. Therefore a lock can be appended to each action as a condition (with `potential` testing either actor or target lock and `allow` requiring both unlocked), while preserving the existing action conditions/effect.

Example evidence-safe restriction shape:

```txt
condition = {
    tooltip = LLM_DIPLOMACY_LOCKED_TT
    potential = {
        OR = {
            has_country_flag = llm_diplomacy_locked
            FROM = { has_country_flag = llm_diplomacy_locked }
        }
    }
    allow = {
        NOT = { has_country_flag = llm_diplomacy_locked }
        FROM = { NOT = { has_country_flag = llm_diplomacy_locked } }
    }
}
```

The exact `condition` semantics are documented by the vanilla header; duplicate top-level key/file merge behavior remains unproven. This supports the parent's plan to preserve the full vanilla diplomatic-actions file and append the condition per action.

## Evidence vs hypothesis

Proven: legacy `which/value/who` export form; `treasury`, `manpower`, `max_manpower`, `stability` numeric value tokens; `is_at_war = yes/no` trigger; `[Root.var.GetValue]` localisation form; `add_opinion = { who = ... modifier = ... }`; Actor/`FROM` scopes; `ai_will_do` trigger block; empty vanilla monthly pulse key.

Hypothesis requiring a live run: `log` strings accept dynamic `[Root.var.GetValue]` interpolation and literal `|` protocol text in the chosen effect; duplicate top-level action/on_action blocks merge rather than replace; an `is_at_war` boolean can be exported numerically. Prefer the branch-to-0/1 pattern for war.
