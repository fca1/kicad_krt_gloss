# Documentation layout

The repository keeps only its user-facing `README.md` at the root.

- `dgloss/doc/` contains the stable gloss specification, implementation notes,
  data sheet and public Python API documentation.
- `docs/reports/` contains historical milestone and validation reports.
- `docs/` contains project-wide attribution and release documents.
- `KRT/` is an external submodule and follows its own documentation layout.

New milestone or test reports whose names contain `_REPORT` must be stored in
`docs/reports/`. Do not add another Markdown file at the repository root.
