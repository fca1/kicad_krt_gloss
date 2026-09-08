# Documentation layout

- [Guide de reprise du projet](REPRISE_PROJET.md) : état intégré, règles,
  subtilités, pistes non intégrées et limites de validation.
- [Architecture](ARCHITECTURE.md) : responsabilités des modules et caches.

- [PACK0](PACK0.md) defines the project's five reference boards for runtime
  measurements and regression checks; [PACK0.json](PACK0.json) records their hashes.

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
