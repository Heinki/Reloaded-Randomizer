#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
launcher="$script_dir/../CnCReloadedRandomizer.exe"
apworld="$script_dir/Archipelago/cnc_reloaded.apworld"
published_apworld="$script_dir/../cnc_reloaded.apworld"

"$script_dir/build_exe_wine.sh" --output "$launcher"
python3 "$script_dir/Archipelago/build_apworld.py" \
    --output-directory "$script_dir/Archipelago"
cp -- "$apworld" "$published_apworld"

test -s "$launcher"
test -s "$apworld"
test -s "$published_apworld"

printf 'Built release pair:\n  %s\n  %s\n' \
    "$launcher" "$published_apworld"
