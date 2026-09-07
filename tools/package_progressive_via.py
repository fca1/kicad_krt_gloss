"""Build an installable PCM ZIP with the diagnostic via prototype activated."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import package_pcm


def main():
    root=package_pcm.ROOT
    cache=root/'dist/KiCadKrtGloss-0.1.3.zip'
    def cached_binaries(destination):
        destination.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(cache) as archive:
            for name in package_pcm.BINARIES:
                (destination/name).write_bytes(archive.read('plugins/KRT/rust_router/'+name))
    package_pcm._download_binaries=cached_binaries
    target=package_pcm.build(root/'dist/prototype-via-fc23d42')
    with zipfile.ZipFile(target) as archive:
        contents={entry.filename:archive.read(entry) for entry in archive.infolist()}
    contents['plugins/dgloss/via_mobile.py']=(root/'tools/progressive_via.py').read_bytes()
    contents['plugins/PROTOTYPE_VIA.md']=('Prototype via mobile fc23d42, activated in this ZIP.\n'
        'Production repository remains unchanged. Absorb null segments and continue until a pad or fixed junction.\n'
        'Experimental: known length-reduction losses on three PACK0 nets, under investigation.\n'
        'Install using KiCad PCM / Install from File. This replaces the normal plugin; reinstall the stable ZIP to revert.\n'
        'G4 keeps the existing user setting; disable it to reproduce the diagnostic tests.\n').encode()
    metadata=json.loads(contents['metadata.json'])
    metadata['name']=metadata.get('name','Smooth Gloss KRT')+' (prototype via)'
    contents['metadata.json']=json.dumps(metadata,indent=2).encode()
    output=target.with_name('KiCadKrtGloss-0.1.3-prototype-via-fc23d42.zip')
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in sorted(contents.items()): archive.writestr(name,content)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read('plugins/dgloss/via_mobile.py')==(root/'tools/progressive_via.py').read_bytes()
    output.with_suffix('.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'\n')
    print(output)


if __name__=='__main__': main()
