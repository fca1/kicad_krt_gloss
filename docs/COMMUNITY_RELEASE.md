# Community testing release — 0.1.4

Updated 12 October 2026. This procedure describes the repository tools; it does
not establish that a GitHub release or PCM catalogue entry has been published.

## Release baseline

- Package **0.1.4**, status **testing**, KiCad **10.0–10.99**, SWIG runtime.
- PCM identifier: `com.github.fca1.kicadkrtgloss`. Public project name:
  **KiCad KRGloss**; installed action and PCM name: **KiCad KRT Gloss**.
- Only the Gloss action is included, with General, Gloss, Log and About tabs.
- KRT **0.23.0**, pinned to `9577628635e3de81d2c1fd8ac882254c0fa7d032`;
  upstream sources unchanged. Official binaries are packaged for Windows
  x86-64, Linux x86-64 and macOS x86-64/arm64. Only Windows has local runtime
  validation for this release.

See [release notes](RELEASE_NOTES_0.1.4.md) and the
[local deployment report](reports/GLOSS_DEPLOYMENT_2026_10_12.md).

## Prepare without a ZIP

Run from the repository root with Python and the KRT submodule available.
Record the source revision and inspect existing changes:

```powershell
git status --short
git rev-parse HEAD
git submodule status KRT
```

Check version agreement between `package_pcm.py`, `kicad_krt_gloss/version.py`
and `kicad_krt_gloss/metadata.json`. Preserve unrelated changes and exclude
unreviewed runtime changes from delivery. The publication tool records HEAD,
but does not prove that the worktree is clean.

Choose a new output directory:

```powershell
python package_pcm.py --stage-only --output-dir .build/deploy-0.1.4
```

This creates `unpacked/metadata.json`, `unpacked/plugins/` and
`unpacked/resources/icon.png`, without a ZIP. It requires network access to
download four official binaries matching `KRT/VERSION`. The local untracked
`KRT/rust_router/grid_router.pyd` is excluded from packaging.

## Local installation, acceptance and rollback

1. Close PCB Editor before replacing the plugin. Back up the existing plugin
   directory outside KiCad's plugin discovery paths and record its location.
2. Copy the **contents** of `unpacked/plugins/` into the plugin installation
   directory. The validated workstation uses
   `C:/Users/frant/Documents/KiCad/10.0/3rdparty/plugins/com_github_fca1_kicadkrtgloss`.
   Resolve the actual user path on other machines. Do not copy the entire
   `unpacked/` directory or leave duplicate plugin installations.
3. Compare installed files with staging, excluding Python caches. Verify the
   version and packaged Rust extension loading with KiCad's Python. A loaded
   Windows extension is locked: close the process before replacing it; reuse
   a binary only after verifying SHA-256 equality.
4. Reopen PCB Editor on a **copy** of a board. Check the four tabs,
   Add/Replace/Clear, remembered branches and whole-net scope. Exercise Gloss,
   corridor, movable vias and the changes overlay. Check that copper outside
   the selected scope is preserved. Inspect the result and run KiCad DRC.
   Record the board hash, options and results.
5. If acceptance fails, close PCB Editor, move the failed installation outside
   discovery paths and restore the backup to its original location. Verify
   loading again on the board copy.

Manual replacement does not update PCM's registry. On the validated workstation
PCM may still show 0.1.3 although the installed module is 0.1.4. The deployment
of `d1897cb` passed native checks; interactive acceptance in PCB Editor remains
unrecorded. Do not describe it as fully qualified.

## Publication kit — only on explicit archive request

**Both commands below create a ZIP.** They require an explicit archive request
and are not part of documentation-only preparation. Use a new empty output
directory. The complete kit also requires Python `jsonschema`.

```powershell
python tools/prepare_publication.py --output-dir dist/publication-0.1.4
```

The kit includes `KiCadKrtGloss-0.1.4.zip`, its `.meta.json` sidecar,
`SHA256SUMS.txt`, external PCM metadata and icon, README and illustrations,
`BUILD.json`, generated `RELEASE_NOTES.md`, `PUBLIER.md`, and an extracted copy.
It validates metadata against the downloaded official v2 schema, archive
integrity, README links and binary presence. It does not execute the binaries.

The generator still writes the earlier PACK0 summary into its release notes.
Replace the generated `RELEASE_NOTES.md` with the reviewed
[0.1.4 notes](RELEASE_NOTES_0.1.4.md) before publication, resolve report links
against the published source revision, and add newly completed acceptance
results. Recheck recorded revisions and status. No tag, push or publication
is performed by this script.

To create only the archive and its checksum/size sidecar:

```powershell
python package_pcm.py --output-dir dist/package-0.1.4
```

The installable archive layout is:

```text
metadata.json
plugins/
  __init__.py
  dgloss/
  KRT/
  ...
resources/
  icon.png
```

## Publication handoff

After acceptance and authorization to publish, follow the generated
`PUBLIER.md`: verify the source commit and availability of tag `v0.1.4`,
publish a testing/pre-release with the plugin ZIP and `SHA256SUMS.txt`, then
verify that its public download returns the exact archive hash. Never silently
replace an existing release or advertise an unverified download URL.

For a PCM catalogue submission, use the generated external metadata containing
the URL, SHA-256 and sizes, after verifying the current catalogue submission
requirements. Internal ZIP metadata intentionally has no download fields.
Changes to archive content, name or tag require regeneration and verification
of the affected assets. The full publication kit is not the installable ZIP.

MIT licence; DrAndyHaas's KRT notices are retained. Frantz is the author and
maintainer, assisted by ChatGPT/Codex (OpenAI). See [AUTHORS.md](AUTHORS.md)
and [NOTICE](../NOTICE).
