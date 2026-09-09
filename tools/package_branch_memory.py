"""Build a test-only PCM ZIP with remembered EB selection activated."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import package_pcm


def main():
    revision = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip()
    base = package_pcm.build(ROOT / 'dist' / ('test-eb-' + revision))
    with zipfile.ZipFile(base) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    for name in ('branch_selection_prototype.py', 'branch_scope_list.py',
                 'img_dlg/selection_net_illustration.png'):
        contents['plugins/' + name] = (ROOT / 'kicad_krt_gloss' / name).read_bytes()
    startup = contents['plugins/__init__.py'].decode('utf-8')
    anchor = '    KiCadKrtGlossPlugin().register()'
    assert startup.count(anchor) == 1
    startup = startup.replace(anchor,
        '    from . import action_plugin as _action\n'
        '    from .branch_selection_prototype import activate as _activate_eb\n'
        '    _restore_eb_prototype = _activate_eb(_action)\n\n' + anchor)
    contents['plugins/__init__.py'] = startup.encode('utf-8')
    contents['plugins/PROTOTYPE_EB.md'] = (
        f'EB selection prototype based on {revision}, activated in this ZIP.\n'
        'Includes per-net branch memory, compact EB column (blank for whole net),\n'
        'two selection illustrations, larger calculation fonts and 0.1 mm solid User copies.\n'
        'Reimport branches after their tracks are replaced. Test on board copies.\n'
        'Native Windows checks only; Linux/macOS not qualified.\n').encode('utf-8')
    metadata = json.loads(contents['metadata.json'])
    metadata['name'] += ' (prototype EB)'
    contents['metadata.json'] = json.dumps(metadata, indent=2).encode('utf-8')
    target = base.with_name(f'KiCadKrtGloss-{package_pcm.VERSION}-prototype-EB.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(contents.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name in ('branch_selection_prototype.py', 'branch_scope_list.py',
                     'img_dlg/selection_net_illustration.png', 'settings_dialog.py'):
            assert archive.read('plugins/' + name) == (ROOT / 'kicad_krt_gloss' / name).read_bytes()
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest + '\n', encoding='utf-8')
    print(target)
    print('sha256=' + digest)


if __name__ == '__main__':
    main()
