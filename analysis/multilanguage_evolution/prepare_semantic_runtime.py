"""Recreate the isolated Linux semantic runtime from checked-in download seals."""
import argparse,hashlib,io,json,subprocess,sys,tarfile
from pathlib import Path
import requests
HERE=Path(__file__).resolve().parent
def fetch(lock,key):
    r=requests.get(lock[key],timeout=180);r.raise_for_status();data=r.content
    expected=lock.get('sha256',lock.get('archive_sha256'))
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Download differs from frozen checksum')
    return data
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
    if sys.version_info[:2]!=(3,12):raise RuntimeError('The historical Python grammar requires CPython 3.12')
    root=a.root.resolve();root.mkdir(parents=True,exist_ok=True);packages=root/'packages'
    subprocess.run([sys.executable,str(HERE/'prepare_linux_runtime.py'),'--output',str(packages),'--lock',str(HERE/'detectors/linux-wheel-lock.json')],check=True)
    lock=json.loads((HERE/'detectors/legacy-runtime-lock.json').read_text());data=fetch(lock,'source')
    prefix='Python-'+lock['version'].split()[-1]+'/Lib/'
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            if member.isfile() and member.name.startswith(prefix+'lib2to3/'):
                relative=Path(member.name[len(prefix):])
                if '..' in relative.parts:raise ValueError('Unsafe legacy source path')
                dest=packages/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
    lock=json.loads((HERE/'detectors/java/runtime-lock.json').read_text());data=fetch(lock,'url');jdk=root/'jdk';jdk.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:tar.extractall(jdk,filter='data')
    javac=next(jdk.glob('*/bin/javac'));java=javac.with_name('java');classes=root/'classes';classes.mkdir(exist_ok=True)
    subprocess.run([str(javac),'-d',str(classes),str(HERE/'detectors/java/SemanticScan.java')],check=True)
    (root/'runtime-paths.json').write_text(json.dumps({'parser_python':sys.executable,'parser_packages':str(packages),'java':str(java),'java_classes':str(classes)},indent=2)+'\n')
    print((root/'runtime-paths.json').read_text())
