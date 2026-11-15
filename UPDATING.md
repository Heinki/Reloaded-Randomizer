# Launcher updates through GitHub Releases

The packaged Windows launcher checks this project's public GitHub repository
after startup. Checks run in the background. Offline access, rate limits, or an
incomplete release do not prevent playing. Source launches do not check for or
install executable updates.

The **Check for updates** button stays visible when the startup check fails or
finds no newer version. Clicking it retries and displays the result, including
network or metadata errors. Finding a newer release changes the button to **Update**.
The launcher log records skipped, started, failed, current, and available checks.
Notice persistence failures are logged without suppressing the update prompt.

When a newer stable release is available, the launcher shows one automatic
update prompt per version. Choosing **No** or closing the prompt remembers that
version across launcher restarts. An **Update** button remains in the upper
right corner, including when Details are hidden. A different newer release can
prompt again. Notice history is stored in the launcher's data directory under
`updates/state.json`, separately from run saves and player settings.

Accepting downloads the launcher and matching APWorld from the same release,
checks their sizes and SHA-256 checksums, closes the launcher, replaces both
files in the game folder, and restarts it. The helper is a temporary copy of the
existing launcher; no Python installation, account, service, or extra installer
is required. The installation directory must be writable. Keep the original
launcher filename.

Updates are postponed while a mission, multiplayer connection, or launcher
operation is active. No game process is terminated. Run saves, settings, maps,
game files, and progression are not replaced. Save-format compatibility still
depends on the new release; finishing a run before updating remains an option.

The matching APWorld is placed beside the launcher. Players must install it in
their separate Archipelago installation before generating a new multiworld.
Do not mix launcher/APWorld releases within an existing multiworld.

## Publishing manually

Rebuild the matching APWorld whenever its bundled Python modules or static
configuration changes. The combined release builds produce both assets.

1. Increment `APP_VERSION` in `randomizer/core/version.py`. Use a dotted numeric
   version and a matching GitHub tag, such as `v3.0` for `3.0`.
2. Build with `build_archipelago_release.ps1`, or `build_all_linux.sh` when using
   Wine. Both workflows prepare `release_manifest.json` and `SHA256SUMS.txt`
   alongside the launcher and APWorld. For other manual builds, run:

   ```sh
   python tools/write_release_manifest.py --launcher /path/to/CnCReloadedRandomizer.exe --apworld /path/to/cnc_reloaded.apworld --output-directory release
   ```

3. Create a draft GitHub release and attach the launcher, matching APWorld,
   `release_manifest.json`, `SHA256SUMS.txt`, and the generated Archipelago setup
   guide. The tag-triggered GitHub build
   also prepares a draft with these assets; it does not publish it automatically.
   If that tag already has a published release, CI skips release uploads and
   keeps the verified bundle in the workflow run's artifacts. Existing drafts
   receive the new build assets. Release lookup and upload errors still fail CI.
4. Publish when ready and mark the release as latest. Drafts and prereleases
   never trigger stable update prompts. Normal commits do not trigger prompts.

The updater requires both product assets. It prefers a manifest whose launcher
version matches the tag and rejects a malformed manifest. Without a manifest,
newer launchers use the SHA-256 digests returned by GitHub's release API for both
assets. Missing checksums still prevent installation. Always attach the manifest:
older installed launchers require it even when GitHub supplies asset digests.
CI validates the complete release bundle, including all checksums and the
APWorld archive version. Version-tag builds also require the tag to match
`APP_VERSION` before uploading. Uploading only an EXE is insufficient. Upload all
assets before publishing. Build a new version rather than changing the assets
of an already published release.

Players on versions without the updater must download an updater-enabled
launcher manually once. They can then accept future releases inside the launcher.

## Repairing missing release metadata

Reloaded V2.2, Mental Omega V1.49, and DTA V2.7 were published with only their
EXE and APWorld. Older updaters reject these releases before showing a prompt.
Attach a format-1 `release_manifest.json` with `launcher_version` matching the
published tag and `files` mapping the published EXE/APWorld names to SHA-256
values. Use GitHub's asset `digest` values or hashes of the downloaded published
files. Never use hashes from a local rebuild, even with the same version.
Adding this missing metadata restores discovery for existing updater-enabled
launchers below that release version without replacing either published asset.

Players already on the latest version correctly receive no update prompt.
Source launches skip executable updates. Same-version local builds and normal
commits do not create a newer public release. The checksum fallback and visible
retry button take effect after installing a repaired build.

## Recovery and verification

Downloads and helper files live in a unique directory under `updates/update-*`
inside the launcher's data directory. Previous launcher/APWorld files remain in
that directory's `backup` subfolder. Replacement or restart-launch failures
restore previous files when possible; any failed restoration displays the
backup location for manual recovery. This is not a health check of the new
launcher's startup or gameplay. After a successful update, old update directories
can be removed once the player no longer needs their backups.

The updater uses HTTPS and the release's published SHA-256 values. These detect
damaged or mismatched downloads; they are not independent publisher signatures.

