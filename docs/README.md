# Documentation layout

The repository keeps only its user-facing `README.md` at the root.

- `dgloss/doc_fr/` contains the French gloss specification, implementation
  notes, data sheet and public Python API documentation.
- `dgloss/doc_en/` contains the matching English translations of those
  first-level documents. Nested documentation is not translated automatically.
- `docs/reports/` contains historical milestone and validation reports.
- `docs/` contains project-wide attribution and release documents.
- `KRT/` is an external submodule and follows its own documentation layout.

New milestone or test reports whose names contain `_REPORT` must be stored in
`docs/reports/`. Do not add another Markdown file at the repository root.
