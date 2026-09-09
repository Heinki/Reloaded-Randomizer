# C&C Reloaded Randomizer Configuration

This directory contains Reloaded-owned static configuration. Required JSON
documents use `schema_version: 1` and a top-level `sections` object. Invalid or
modified packaged configuration stops launcher startup.

The active faction order is Allies, Soviets, Yuri, GDI, and Nod. CABAL is
deferred and must not be added through inferred ownership.

## Main configuration

- `ui.json`: campaign labels, progression/reward modes, faction colors, themes
- `default_player_config.json`: initial launcher choices
- `missions.json`: progression policy, finale multipliers, victory hooks,
  objective counts, starters, and map-specific exceptions
- `mission_catalogue.json`: source-hash-bound facts for all 108 missions
- `factions.json`: five-faction production families
- `production_topology.json`: factories, MCVs, engineers, harvesters, and
  clone/production safety evidence
- `tier_one.json`: reviewed unit and defense starters for five factions
- `shop_mode.json`: Reloaded Shop economy, run settings, Command Coins,
  mission effects, exclusions, and exact unit/power prices
- `archipelago.json`: Reloaded APWorld/client compatibility
- `map_rules.json`: generated namespaces and engine/parser limits

## Reward configuration

Files under `rewards/` define the active Reloaded access catalogue, 14 unit
buff types, 18 powers, compatible power buffs, player/helper clone tuning,
explicit AI Enemy Rewards using Mental Omega defaults,
and empty-by-design special building lists.

Player unit clones use `RLRP`; cloned weapons use `RLRW`. These clones are for
future player production. Map-authored placements, TaskForces, triggers,
events, and actions must retain native identities.

Player-production clones preserve each source TechnoType's authored
`UIDescription`, keeping Phobos sidebar tooltips available for Shop Mode units
and their buffed variants. `clone_policy.ui_description` in
`rewards/tuning.json` is used only when a source type has no description.

`reloaded_content_catalogue.json` and `reloaded_balance_catalogue.json` retain
the broader installed-rule evidence. Runtime reward construction uses only the
approved five-faction subset in `randomizer/rewards/reloaded_definitions.py`.

## Shop Mode content

`shop_mode.json` owns Shop-only balance. `settings.excluded_reward_ids` accepts
canonical reward names and removes those rewards before inventory construction.
Keep it empty unless a reviewed Reloaded reward is unsafe or unusable in Shop
Mode.

The first two Shop missions offer Standard choices, including a fixed-unit or
hero mission when available. From mission 3 onward, every remaining eligible
mission has equal selection probability, regardless of class or run length.
All three choices can be finales. Completed missions cannot repeat, and the
configured mission pool still applies.

The former `stage_class_weights` section is no longer used; older configuration
files containing it remain loadable. `stage_difficulty_weights` still controls
the separate in-game difficulty curve.

`unit_target_prices` must exactly cover every Reloaded unit target exposed by
the Shop catalogue. Each uppercase TechnoType ID has `run_access`, `run_buff`,
`permanent_access`, and `permanent_buff`. Use `null` only when that target has no
matching access or buff reward. `power_target_prices` follows the same rule for
SuperWeaponType IDs, with `run_access` and `run_buff`. Missing, unknown, or
availability-mismatched targets stop startup instead of silently receiving a
default price.

`mission_effects` defines deterministic temporary boons and AI challenges.
Every entry requires a unique `title`, a `description`, non-negative
`bonus_run_coins` and `bonus_meta_coins`, plus exactly one of
`player_reward_ids` or `enemy_reward_id`. Optional `exclusive_reward_ids`
prevents a boon from being offered when its defining power is already active.
Optional `buffs_allied_helpers` defaults to `false`.

`stage_difficulty_weights` independently controls the actual in-game Casual,
Normal, and Hard difficulty of every visible offer. Profiles use ascending run
percentage boundaries ending at 100. Difficulty is derived from run seed,
stage, and mission code without consuming mission-selection RNG. Stages 1–3
are Casual-heavy, stages 4–5 are Normal-heavy, stages 6–7 introduce Hard, and
stages 8–10 weight Normal and Hard equally. Difficulty Assist lowers only its
chosen offer by one step.

After reviewing a changed Reloaded reward catalogue, regenerate explicit target
coverage with:

```powershell
python tools\rebuild_shop_target_prices.py
```

This preserves Reloaded's configured TechLevel tier values for units and uses
Reloaded-specific offensive, secondary, and aid power price bands. Review the
resulting diff; this command is not a substitute for balance review.

## Player state

Source runs write `player/cnc_reloaded_randomizer.yaml`. Packaged builds use:

```text
ReloadedRandomizerData/configs/player/cnc_reloaded_randomizer.yaml
```

Do not commit player seeds, credentials, or generated room state.

## Validation and regeneration

```powershell
python -c "from randomizer.config.static import REQUIRED_STATIC_CONFIGS, validate_static_configs; validate_static_configs(REQUIRED_STATIC_CONFIGS)"
python -m randomizer.audit
python -m Archipelago.audit
```

Source-derived review files can be regenerated with the tools under `tools/`.
Do not use reset options unless reviewed overlays and policy are intentionally
being discarded.
