from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "docs" / "reports"


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
