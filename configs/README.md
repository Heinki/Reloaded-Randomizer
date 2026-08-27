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
- `shop_mode.json`: Reloaded Shop economy, run settings, and Command Coins
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

`reloaded_content_catalogue.json` and `reloaded_balance_catalogue.json` retain
the broader installed-rule evidence. Runtime reward construction uses only the
approved five-faction subset in `randomizer/rewards/reloaded_definitions.py`.

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
