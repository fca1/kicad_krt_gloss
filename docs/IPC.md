# Gloss IPC — development version 0.1.5

The IPC action runs outside PCB Editor. All live board operations use
`kicad-python` 0.8.0. KRT 0.23.1 remains unmodified and supplies geometry,
clearance and electrical validation. There is no pcbnew fallback in this action.

## Installation

Prepare a directory without creating a ZIP:

```powershell
python package_pcm.py --stage-only --output-dir .build/ipc-install
```

Copy the **contents** of `.build/ipc-install/unpacked/plugins` into
`Documents/KiCad/10.99/plugins/com.github.fca1.kicadkrtgloss`.
Enable the API server in KiCad preferences and restart the editor. KiCad
creates a Python environment using `requirements.txt`; launch KRT Gloss from
the toolbar. The launcher requires KiCad's instance-specific socket environment
and never guesses which of multiple open editors to modify.

The rule-reading commands require a sufficiently recent 10.99 / 11 build.
Version 10.99.0-2520-g89476220a8 is the validation target. Capability failures
stop the action; this is not a claim of support for every nightly build.
The historical SWIG sources remain for comparison and KiCad 10 regression tests;
the IPC manifest and distribution metadata select the external IPC action.

## Behavior and limits

- Selection, Add/Replace/Clear, remembered branches and whole-net scope remain.
  Net/branch highlighting is unavailable, as explicitly accepted by the user.
- A fresh live snapshot and live minimums/net classes feed KRT. UUIDs and net
  names identify objects; IPC net codes are not assumed to match the parser.
- KiCad 11 footprint `transform` poses are converted in the private snapshot
  only when scale is exactly (1, 1). Scaled or unknown transforms are refused.
- KiCad's custom-rule IPC omits arbitrary layer masks. The sibling saved
  `.kicad_dru` remains authoritative for their syntax, as on the native path.
  The adapter compares names, conditions, constraints, severity and represented
  layers against live IPC rules and refuses mismatches. Unrepresented layer-only
  changes cannot be verified through this API; save custom rules before Gloss.
  Named/option-bearing constraints outside the adapter's coverage are refused.
- Every result still requires G5. A changed board or rules snapshot prevents
  publication. Track creation and via movement are checked against their IPC
  receipts; deletion statuses are checked individually. A failed transaction
  is dropped. The successful copper change is one Undo operation.
- Zone refill follows publication. A refill failure reports that copper was
  applied and requires Undo or refill/DRC. G5 is not a full KiCad DRC.
- Optional before/after drawings belong to `KRT Gloss changes (IPC)` on a free,
  enabled User layer. If all such layers are occupied, the drawing is skipped.
- No source board is saved by Gloss. A no-op creates no Undo transaction.

## Protocol provenance

`ipc_protocol.pb` is a private descriptor pool for the KiCad rule-reading
commands missing from kicad-python 0.8.0. Corresponding sources are included
in `ipc_protocol_sources/`, from KiCad commit
`dcadf9baa30d43d7d1b3d0342345f05ec0da26e1`; Google protobuf sources are v29.6.
Generate a descriptor set with protoc 29 and `--include_imports`, using
`board/board_commands.proto` as input. See `IPC_PROTOCOL_NOTICE.txt` and the
included GPL and protobuf license texts. Existing MIT source notices remain.

## Acceptance

`tools/check_ipc_gloss.py` requires an explicit socket and expected board path.
Use only a disposable copy for `--apply`: the tool applies Gloss, checks copper
outside the selected net and uses one Undo to verify restoration. It never
saves the board. `--branches` exercises remembered branches and `--corridor`
exercises the corridor option. Unit tests are in `tests/test_ipc.py`.
