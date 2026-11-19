# Gloss IPC — version 0.1.5

The IPC action runs outside PCB Editor. All live board operations use
`kicad-python` 0.8.0. KRT 0.24.1 remains unmodified and supplies geometry,
clearance and electrical validation. There is no pcbnew fallback in this action.

## Installation

From a checkout of the release tag, initialize the pinned KRT submodule and stage the plugin:

```powershell
git submodule update --init --recursive
python package_pcm.py --stage-only --output-dir .build/ipc-install
```

Copy the **contents** of `.build/ipc-install/unpacked/plugins` into
`Documents/KiCad/10.99/plugins/com.github.fca1.kicadkrtgloss`.
Enable the API server in KiCad preferences and restart the editor. KiCad
creates a Python environment using `requirements.txt`; launch KRT Gloss from
the toolbar. The launcher requires KiCad's instance-specific socket environment
and never guesses which of multiple open editors to modify.

The rule-reading commands require a sufficiently recent 10.99 / 11 build.
The current validation target is `10.99.0-6738-g3f3d8fbe5e` ([acceptance report](reports/KRT_0241_KICAD_6738.md)); the initial IPC
validation used `10.99.0-2520-g89476220a8`. Capability failures
stop the action; this is not a claim of support for every nightly build.
The failure recorded during the [performance review](reports/GLOSS_IPC_PERFORMANCE_2026_10_21.md)
on build 5583 is resolved by a targeted adapter: `GetNetClasses` now names the
board's project explicitly and includes the terminal path separator required
by that build's project validator. Only the request is normalized; the board's
document identity remains unchanged. The adapter uses the private descriptor
pool and keeps kicad-python 0.8.0 and its global descriptors unchanged.
Live import, application and Undo have passed on disposable copies on build
5583, including remembered `/A` branches, `/B` via movement and corridor mode.
The complementary [toolbar, zones and DRC acceptance](reports/IPC_TOOLBAR_ZONES_DRC_2026_10_21.md)
also passes on build 5583 with the installed plugin: a real toolbar click,
two initially empty zones filled by Gloss, and no reported DRC violations or
unconnected items before or after the change on the synthetic fixture.
The historical SWIG sources remain for comparison and KiCad 10 regression tests;
the IPC manifest and distribution metadata select the external IPC action.

## Behavior and limits

- Selection, Add/Replace/Clear, remembered branches and whole-net scope remain.
  Net/branch highlighting is unavailable, as explicitly accepted by the user.
- A fresh live snapshot and live minimums/net classes feed KRT. UUIDs and net
  names identify objects; IPC net codes are not assumed to match the parser.
- During the initial `Run`, selection inspection, dialog preparation and
  initial branch capture share one consistent snapshot. This reuse ends when
  `Run` returns, including on failure, before the dialog event loop begins.
  Every subsequent Add, Replace or Gloss action imports the live board again.
  The direct single-net run and dialog runs retain the live-state checks
  before publication; reuse never authorizes applying a stale result.
- KiCad 11 footprint `transform` poses are converted in the private snapshot
  only when scale is exactly (1, 1). Scaled or unknown transforms are refused.
  Converted poses and untouched text are assembled as fragments in one pass,
  avoiding a full snapshot copy for every footprint. Pose validation and the
  refusal of unsupported transforms remain unchanged.
- KiCad's custom-rule IPC omits arbitrary layer masks. The sibling saved
  `.kicad_dru` remains authoritative for their syntax, as on the native path.
  The adapter compares names, conditions, constraints, severity and represented
  layers against live IPC rules and refuses mismatches. Unrepresented layer-only
  changes cannot be verified through this API; save custom rules before Gloss.
  Named/option-bearing constraints outside the adapter's coverage are refused.
- Every result still requires G5. A changed board or rules snapshot prevents
  publication. Track creation and via movement are checked against their IPC
  receipts; via updates preserve the original UUID and all properties except
  position (the SDK's creation-oriented `clone()` clears the UUID). The receipt
  must contain exactly the requested via UUIDs and positions. Deletion statuses
  are checked individually. A failed transaction
  is dropped. The copper change is one transaction. On build 5583, zone refill
  adds a separate native transaction: the tested case requires two Undo
  operations, first to remove the fill and then to restore the original copper.
- Zone refill is requested after publication. Recent 10.99 editor builds
  acknowledge a refill of all zones before it finishes; the request returning
  does not establish completion or a successful DRC. A refill request failure
  reports that copper was applied and requires Undo or refill/DRC. G5 is not
  a full KiCad DRC. Completion has been verified on the acceptance fixture by
  observing initially empty zones become filled with stable, nonempty polygons,
  then running DRC on the exported live state without another refill.
- Optional before/after drawings belong to `KRT Gloss changes (IPC)` on a free,
  enabled User layer. If all such layers are occupied, the drawing is skipped.
- No source board is saved by Gloss. A no-op creates no Undo transaction.
- Closing the tested IPC dialog hides it but leaves its Python processes
  running. The modeless dialog's close handler does not destroy the window,
  so the external wx event loop remains alive. This existing lifecycle defect
  is documented in the toolbar acceptance report and is not corrected by it.

## Protocol provenance

`ipc_protocol.pb` is a private descriptor pool for KiCad rule reads and the
explicit project field of `GetNetClasses` missing from kicad-python 0.8.0.
Corresponding sources are included
in `ipc_protocol_sources/`, from KiCad commit
`dcadf9baa30d43d7d1b3d0342345f05ec0da26e1`; Google protobuf sources are v29.6.
Generate a descriptor set with protoc 29 and `--include_imports`, using
both `board/board_commands.proto` and `common/commands/project_commands.proto`
as inputs. The additional project command uses the same pinned KiCad source;
this adaptation does not update the protocol provenance or the SDK.
See `IPC_PROTOCOL_NOTICE.txt` and the
included GPL and protobuf license texts. Existing MIT source notices remain.

## Acceptance

`tools/check_ipc_gloss.py` requires an explicit socket and expected board path.
Use only a disposable copy without zone refill for `--apply`: the tool applies Gloss, checks copper
outside the selected scope (including other branches of the same net), compares
live tracks and vias with the certified KRT geometry at nanometre precision,
and uses one Undo to verify restoration. It never saves the board. `--branches`
exercises remembered branches, `--corridor` exercises the corridor option and
`--stale-check --apply` verifies rejection after a temporary live edit.
Cleanup follows actual transaction publication, including zero-length gains
and errors after publication.

`tools/check_ipc_dialog.py` runs the actual installed entry point and wx dialog
with `--plugin-root`, `--socket`, `--expected-board` and optional `--output` JSON.
On the disposable fixture without zones it exercises Add/Replace/Clear, branch memory despite
a changed native selection, the real Gloss worker/progress dialog, G5,
application and one Undo. It checks source integrity and that pcbnew stays
unloaded. This is a programmatic dialog exercise, not a toolbar click test.
Unit tests are in `tests/test_ipc.py`, `tests/test_ipc_project.py` and
`tests/test_ipc_bridge.py`.

These two scripts assume one Undo for cleanup; do not use their apply recipes
to validate a board whose refill adds a transaction. For toolbar, zone refill
and DRC acceptance, copy `tests/fixtures/ipc_zones/` and follow its README and
the [recorded procedure](reports/IPC_TOOLBAR_ZONES_DRC_2026_10_21.md).
`tools/check_ipc_drc.py BEFORE.json AFTER.json` compares native DRC reports,
requiring the same declared version, units and coverage. Exit 0 means no new
findings, not necessarily a clean board; unchanged ignored checks remain
outside coverage. Its 18 unit tests are in `tests/test_ipc_drc.py`.
