"""Package the isolated support prototype, without changing production files."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    base = ROOT / 'dist/test-review-e3f5745/KiCadKrtGloss-0.1.3.zip'
    with zipfile.ZipFile(base) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    protected_name = 'plugins/dgloss/protected_centering.py'
    protected = contents[protected_name].decode('utf-8')
    start = protected.index('def build_protected_path(')
    end = protected.index('\ndef certify_passages(', start)
    protected = protected[:start] + '''def build_protected_path(context, doors, deadline=None):
    from .support_prototype import build_candidate
    audit = []
    candidate = build_candidate(context, doors, deadline, audit=audit)
    for record in audit:
        if record.get('rejected'):
            print('Centering supports prototype rejected: ' + record['rejected'])
    return candidate

''' + protected[end:]
    contents[protected_name] = protected.encode('utf-8')
    interpad_name = 'plugins/dgloss/interpad.py'
    interpad = contents[interpad_name].decode('utf-8')
    start = interpad.index('                yield from _centering_proposals(')
    end = interpad.index('            for selected_doors, candidate in proposals():', start)
    interpad = interpad[:start] + interpad[end:]
    contents[interpad_name] = interpad.encode('utf-8')
    prototype = (ROOT / 'tools/prototype_centering_supports.py').read_text(encoding='utf-8')
    # Package only the construction helpers, not the standalone CLI runner.
    start = prototype.index('def solve_supports(')
    end = prototype.index('\ndef winding(')
    contents['plugins/dgloss/support_prototype.py'] = (
        '"""Experimental fixed-support Centering; not production-qualified."""\n'
        'import math\nfrom time import perf_counter\n\n' + prototype[start:end]).encode('utf-8')
    contents['plugins/PROTOTYPE_CENTERING_SUPPORTS.md'] = (
        'Experimental support-preserving Centering. No historical construction fallback.\n'
        'Requires both multi-door and new-segments options enabled.\n'
        'Fixed unconstrained supports; parallel supports rejected.\n'
        'KRT foreign-obstacle sweep and final G5 retained. General moving self-contact\n'
        'certification remains incomplete. Test on copies, not production boards.\n').encode('utf-8')
    metadata = json.loads(contents['metadata.json'])
    metadata['name'] += ' (prototype Centering supports)'
    contents['metadata.json'] = json.dumps(metadata, indent=2).encode('utf-8')
    target = ROOT / 'dist/test-supports-e3f5745/KiCadKrtGloss-0.1.3-prototype-supports.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(contents.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert b'for half_length in' not in archive.read(protected_name)
        assert b'yield from _centering_proposals(' not in archive.read(interpad_name)
    print(target)
    print('sha256=' + hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
