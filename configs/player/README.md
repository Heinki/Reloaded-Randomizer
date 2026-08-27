# Local Player Configuration

Source runs write `cnc_reloaded_randomizer.yaml` here. Packaged builds use:

```text
ReloadedRandomizerData/configs/player/cnc_reloaded_randomizer.yaml
```

This YAML stores local UI choices, next-seed settings, launch settings, and
reserved future integration settings. Git ignores it, and packaged builds do
not include it.

Static mission, faction, reward, clone, and balance policy belongs in the
parent `configs/` directory or `configs/rewards/`. Never place gameplay policy
or shared defaults in the player YAML.

Old `config/cnc_reloaded_randomizer.yaml` state migrates here automatically
when no active player file exists.
