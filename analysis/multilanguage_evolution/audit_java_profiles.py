"""Freeze compiler compatibility profiles from pinned build descriptors."""
import argparse,hashlib,json,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
import requests
HERE=Path(__file__).resolve().parent
NS={'m':'http://maven.apache.org/POM/4.0.0'}
def sha(b):return hashlib.sha256(b).hexdigest()
def scalar(text):
    if text is None:return None
    text=text.strip();text=text[2:] if text.startswith('1.') else text
    return int(text) if text.isdigit() else None
def pom_release(data):
    try:
        root=ET.fromstring(data)
        for node in root.iter():node.tag=node.tag.split('}')[-1]
    except ET.ParseError:return None
    for node in root.iter():
        name=node.tag.split('}')[-1]
        if name in {'maven.compiler.release','java.level','maven.compiler.source'}:
            value=scalar(node.text)
            if value:return value
    for plugin in root.findall('.//plugin'):
        aid=plugin.find('artifactId')
        if aid is not None and aid.text=='maven-compiler-plugin':
            for tag in ['release','source']:
                node=plugin.find('configuration/'+tag)
                if node is not None and scalar(node.text):return scalar(node.text)
    return None
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path,required=True);a=ap.parse_args();records=[];parents={}
    for repo in ['jenkinsci__jenkins','apache__tomcat']:
        h=json.loads((HERE/'selection/histories'/f'{repo}.json').read_text())
        for obs in h['observations']:
            descriptor='pom.xml' if repo.startswith('jenkins') else 'build.xml'
            p=subprocess.run(['git','--git-dir='+str(a.cache/repo),'show',obs['commit']+':'+descriptor],capture_output=True,check=True);data=p.stdout;evidence=[{'path':descriptor,'sha256':sha(data)}];declared=None
            if repo.startswith('jenkins'):
                declared=pom_release(data)
                if declared is None:
                    root=ET.fromstring(data)
                    for node in root.iter():node.tag=node.tag.split('}')[-1]
                    parent=root.find('parent')
                    if parent is not None:
                        group=parent.find('groupId').text;artifact=parent.find('artifactId').text;version=parent.find('version').text
                        url='https://repo.jenkins-ci.org/releases/'+group.replace('.','/')+'/'+artifact+'/'+version+'/'+artifact+'-'+version+'.pom'
                        if url not in parents:
                            response=requests.get(url,timeout=45)
                            parents[url]=response.content if response.status_code==200 else None
                        parent_data=parents[url]
                        if parent_data:
                            declared=pom_release(parent_data);evidence.append({'url':url,'sha256':sha(parent_data),'descriptor':parent_data.decode('utf8','replace')})
            else:
                root=ET.fromstring(data)
                props={n.attrib.get('name'):n.attrib.get('value') for n in root.iter('property')}
                declared=scalar(props.get('compile.release')) or scalar(props.get('compile.source'))
            # Missing inherited settings are not guessed to be a particular historical JDK.
            compatibility=max(8,declared) if declared else 8 if int(obs['label'][-4:])<=2016 else None
            records.append({'repository':repo,'label':obs['label'],'commit':obs['commit'],'declared_release':declared,'compiler_release':compatibility,'evidence':evidence,'note':'JDK 21 supports release 8 or newer. Earlier declared levels use 8 for source-metric compatibility, not historical build equivalence.' if declared and declared<8 else 'Declared language setting unresolved; Java 8 is an explicit compatibility assumption for these pre-2017 sources, not a recovered build setting.' if declared is None else 'Declared compiler language release.'})
            print(repo,obs['label'],declared,compatibility,flush=True)
    (HERE/'protocols/java-release-profiles.json').write_text(json.dumps(records,indent=2)+'\n')
