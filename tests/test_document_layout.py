from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "docs" / "reports"
DOC_FR = ROOT / "dgloss" / "doc_fr"
DOC_EN = ROOT / "dgloss" / "doc_en"


def _project_markdown_files():
    for path in ROOT.rglob("*.md"):
        relative = path.relative_to(ROOT)
        if relative.parts[0] == "KRT":
            continue
        yield path, relative


def test_readme_is_the_only_root_markdown_file():
    assert sorted(path.name for path in ROOT.glob("*.md")) == ["README.md"]


def test_reports_are_kept_in_the_reports_directory():
    misplaced = [
        relative.as_posix()
        for path, relative in _project_markdown_files()
        if "_REPORT" in path.name.upper() and path.parent != REPORTS
    ]
    assert misplaced == []


def test_gloss_reference_documents_have_french_and_english_versions():
    assert not (ROOT / "dgloss" / "doc").exists()
    french = sorted(path.name for path in DOC_FR.glob("*.md"))
    english = sorted(path.name for path in DOC_EN.glob("*.md"))
    assert french == english == [
        "gloss_dsheet.md",
        "gloss_krt.md",
        "gloss_krt_python_api.md",
        "gloss_work.md",
    ]
