"""Prepare local release assets; never push, tag or publish remotely."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import package_pcm


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit('Choose an empty output directory to preserve earlier releases.')
    archive = package_pcm.build(destination)
    info = json.loads(archive.with_suffix('.meta.json').read_text(encoding='utf-8'))
    metadata = json.loads((ROOT / 'kicad_krt_gloss/metadata.json').read_text(encoding='utf-8'))
    version = metadata['versions'][0]
    assert version['version'] == info['version']
    tag = 'v' + info['version']
    repo = 'https://github.com/fca1/kicad_krt_gloss'
    version.update(download_url=f'{repo}/releases/download/{tag}/{archive.name}',
                   download_sha256=info['sha256'], download_size=info['download_size'],
                   install_size=info['install_size'])
    submission = destination / 'pcm' / metadata['identifier']
    submission.mkdir(parents=True)
    (submission / 'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
    shutil.copy2(ROOT / 'kicad_krt_gloss/icon_64.png', submission / 'icon.png')
    request = urllib.request.Request('https://go.kicad.org/pcm/schemas/v2', headers={'User-Agent':'KRGloss'})
    with urllib.request.urlopen(request, timeout=30) as response:
        schema = json.load(response)
    import jsonschema
    (destination / 'pcm-schema-v2.json').write_text(json.dumps(schema, indent=2)+'\n', encoding='utf-8')
    validator = jsonschema.Draft7Validator(schema)
    with zipfile.ZipFile(archive) as packed:
        assert packed.testzip() is None
        names = set(packed.namelist())
        internal = json.loads(packed.read('metadata.json'))
        validator.validate(internal)
        validator.validate(metadata)
        assert not any('download_' in key for key in internal['versions'][0])
        assert not any(name.endswith(('.lck', '.pyc')) for name in names)
        readme = packed.read('plugins/README.md').decode('utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', readme):
            if not target.startswith(('https:', 'http:', '#')):
                assert 'plugins/' + target in names, target
        for binary in package_pcm.BINARIES:
            assert 'plugins/KRT/rust_router/' + binary in names
        packed.extractall(destination / 'verification-extracted')
    shutil.copy2(ROOT / 'README.md', destination / 'README.md')
    shutil.copytree(ROOT / 'docs/assets', destination / 'docs/assets')
    shutil.copy2(ROOT / 'docs/AUTHORS.md', destination / 'docs/AUTHORS.md')
    for name in ('LICENSE', 'NOTICE'):
        shutil.copy2(ROOT / name, destination / name)
    revision = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    krt = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT/'KRT', text=True).strip()
    (destination / 'BUILD.json').write_text(json.dumps(dict(info, source_commit=revision, krt_commit=krt,
        validation='PCM schema v2, ZIP integrity, README links, four binaries; see release notes for runtime limits'), indent=2)+'\n', encoding='utf-8')
    (destination / 'SHA256SUMS.txt').write_text(f"{info['sha256']}  {archive.name}\n", encoding='utf-8')
    notes = f'''# KRGloss {info['version']} — testing release

Shorten and simplify existing routing with Gloss, or centre tracks through valid gates with Centering.
Select whole nets or remembered elementary branches. Set Proximity max by selecting exactly two pads in KiCad and clicking Refresh.

Requires KiCad 10.x, SWIG runtime. Bundled KRT: {info['krt_version']} ({krt}).
Includes binaries for Windows x86-64, Linux x86-64 and macOS Intel/Apple Silicon.
Install {archive.name} with Plugin and Content Manager → Install from File.
The installed action is currently named “KiCad KRT Gloss”; KRGloss is the public project name.

Author and maintainer: Frantz, with assistance from ChatGPT/Codex (OpenAI).
KRT by DrAndyHaas. MIT licence; upstream notices retained.

Validation scope: targeted compatibility tests were run on Windows after the KRT update.
Linux and macOS binaries are included but no installation test on those systems is claimed.
The earlier PACK0 performance comparisons used the previous KRT revision; they are not a full qualification of this release.
A known perpendicular via-sweep crossing defect remains documented in docs/REPRISE_PROJET.md.
Review the resulting copper and run KiCad DRC before fabrication. This is not a stable release.
'''
    (destination / 'RELEASE_NOTES.md').write_text(notes, encoding='utf-8')
    instructions = f'''# Publication de KRGloss {info['version']}

Fichiers préparés localement ; aucune publication ni tag distant effectué.

1. Vérifier la version sur une copie de carte dans KiCad. Le statut est testing.
2. Publier le commit {revision} et ses sources sur {repo}, puis créer le tag {tag} sur ce commit (vérifier qu'il n'existe pas déjà).
3. Créer une GitHub Release marquée pre-release pour ce tag. Utiliser RELEASE_NOTES.md comme description et joindre {archive.name} ainsi que SHA256SUMS.txt.
4. Vérifier que cette URL publique télécharge exactement le ZIP :
   {version['download_url']}
5. Pour apparaître dans le catalogue PCM officiel, soumettre le dossier pcm/{metadata['identifier']} au dépôt https://gitlab.com/kicad/addons/metadata selon ses instructions. Le metadata.json externe contient URL, tailles et SHA-256 ; celui à l'intérieur du ZIP n'en contient pas.

Ne pas joindre le kit complet comme plugin installable : seul {archive.name} s'installe par PCM.
Si le nom du ZIP, le tag ou son contenu changent, régénérer les métadonnées et le checksum.
BUILD.json conserve les révisions. verification-extracted sert au test local du package.
Référence officielle : https://dev-docs.kicad.org/en/addons/index.html
'''
    (destination / 'PUBLIER.md').write_text(instructions, encoding='utf-8')
    print('Publication kit:', destination)


if __name__ == '__main__':
    main()
