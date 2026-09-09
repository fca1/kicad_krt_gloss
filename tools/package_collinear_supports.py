"""Build current PCM sources with the isolated collinear solver activated."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import package_pcm


def main():
    base = package_pcm.build(ROOT / 'dist/test-colli-7628191')
    with zipfile.ZipFile(base) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    name = 'plugins/dgloss/support_prototype.py'
    source = contents[name].decode('utf-8')
    first = source.index('def solve_supports(')
    last = source.index('\ndef build_candidate(', first)
    prototype = (ROOT / 'tools/prototype_collinear_supports.py').read_text(encoding='utf-8')
    solver = prototype[prototype.index('def solve_supports('):]
    contents[name] = (source[:first] + solver + '\n\n' + source[last:]).encode('utf-8')
    contents['plugins/PROTOTYPE_COLLINEAR.md'] = (
        'Collinear Centering support prototype 7628191, activated in this ZIP.\n'
        'Current enlarged Centering illustration and Proxi controls included.\n'
        'Keep multi-door and new-segment options enabled. No legacy fallback.\n'
        'PACK0 qualification is partial (budgets); general moving self-contact\n'
        'certification remains incomplete. Test on copies of boards.\n').encode('utf-8')
    metadata = json.loads(contents['metadata.json'])
    metadata['name'] += ' (prototype collinear supports)'
    contents['metadata.json'] = json.dumps(metadata, indent=2).encode('utf-8')
    target = base.with_name('KiCadKrtGloss-0.1.3-prototype-colli.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for entry, content in sorted(contents.items()):
            archive.writestr(entry, content)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert solver.encode('utf-8') in archive.read(name)
        assert archive.read('plugins/settings_dialog.py') == (ROOT / 'kicad_krt_gloss/settings_dialog.py').read_bytes()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest+'\n', encoding='utf-8')
    print(target)
    print('sha256='+digest)


if __name__ == '__main__':
    main()
