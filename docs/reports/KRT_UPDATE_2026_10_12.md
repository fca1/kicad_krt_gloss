# KRT update — 12 October 2026

KRGloss 0.1.4 (testing), KRT `529f873d` → `95776286` on upstream main,
reported version 0.23.0. No edits inside KRT. No algorithm changes in Gloss
or Centering were needed by the compatibility checks below.

## Diagnosis and changes

- Baseline targeted tests: 97 passed, one README assertion failed before the
  update. The test required HTML strong tags, but the current illustrated
  README uses Markdown bold. Updated those two assertions, not the guide.
- The local ignored canonical Rust binary predates this update. Tests that
  load it cannot qualify the new distribution. Staged a clean installation
  using official v0.23.0 assets instead; Rust sources at the release tag and
  integrated main revision are identical.
- New `--stage-only` packaging mode tests the actual install layout without
  generating a ZIP. Version metadata, Python version and packager are 0.1.4.
- KRT's dependency gate now imports `startup_checks`; it is already included
  by the existing router-tree copy. Real KiCad dependency check returns True.

Windows binary SHA-256:
`542047fded20cde0cccefa22c2d4782e60d6b8f5a18de68ea4312205ea35771f`.
The staged engine and this content-addressed cached binary were explicitly
identified in a fresh process, including the new Rust `lane_search` export.

## Native acceptance

Used `tools/check_branch_memory_native.py` with `KRG_TEST_PLUGIN_ROOT` pointing
at the staged plugin, KiCad Python `D:/kicad/bin/python.exe`, a detached board,
and no SaveBoard. Board: `test_centering2`, net `/A`, proximity 2.54 mm.
Input SHA-256: `08b5d8efe0990e9753f111b680fd1d95cf6ddb78e82888aa09182422c8f797fb`.

| Action | Scope | Result | Logged engine time |
| --- | --- | --- | --- |
| Gloss | Two remembered EB, corridor off, G4 limit 1 | 85.3560 → 47.8863 mm, 13 → 2 replaced tracks, G5 true | 98.2 ms |
| Centering | Two remembered EB, mandatory preparatory corridor Gloss | Three doors centered, seven tracks replaced by seven, G5 true | 154.4 ms |

These are single timings, not a performance comparison. Tests also cover
Add/Replace/Clear, branch memory, stale UUID rejection, highlight IDs, scope
columns and dialog layout. Outside-scope copper and source-file hash preserved.
Native wx emits existing parent/sizer and teardown warnings; no functional test
failure. This is not visual validation in an open PCB editor.

Final suite including the staging regression: 434 tests passed, one expected
failure on the staged runtime. The expected failure is the previously documented
perpendicular via-sweep crossing case; this update does not fix it.

No PACK0 campaign, Linux/macOS runtime tests, full KiCad DRC or remote release.
No ZIP created. Official binaries for all four packaged platforms downloaded;
only Windows was executed. Existing documented limitations remain applicable.

Local installation replacement was not performed: KiCad was running when the
pre-installation guard checked. The existing 0.1.3 installation remains intact.
The validated 0.1.4 layout is in `.build/krt-0.23.0-validation/unpacked/plugins`;
close KiCad before replacing the installed plugin, retaining the old directory
outside KiCad's plugin search path as a rollback backup.
