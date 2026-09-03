# Community testing release

KiCad KRT Gloss is packaged as a KiCad 10 SWIG ActionPlugin using the official
Plugin and Content Manager archive layout:

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

The PCM identifier is `com.github.fca1.kicadkrtgloss`. Releases remain in
`testing` status while G4 and G5 are under development and target KiCad 10.x.

Build the archive with:

```powershell
py -3.12 package_pcm.py
```

The build downloads the platform binaries matching the KRT submodule version,
creates `dist/KiCadKrtGloss-<version>.zip` and writes its SHA-256 and sizes to a
sidecar `.meta.json` file. Before a PCM submission, publish the archive at the
URL declared in the repository metadata, add the resulting download fields,
then submit the package metadata through the official KiCad addons metadata
repository process.

The package is MIT-licensed and preserves the copyright and primary code
provenance of DrAndyHaas. The standalone adaptation was created with
ChatGPT/Codex (OpenAI); Frantz is co-author and maintainer.
