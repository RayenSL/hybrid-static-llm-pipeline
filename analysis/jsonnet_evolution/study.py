#!/usr/bin/env python3
"""Versioned Json.NET evolution pilot. Python standard library only.

prepare runs wherever Git is available. pilot requires Windows .NET/MSBuild for
legacy projects. replay uses only the sealed runtime, scanner and archived inputs.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def run(command, log, cwd=None):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps([str(x) for x in command]) + '\n')
        stream.flush()
        result = subprocess.run([str(x) for x in command], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command exited {result.returncode}; see {log}')


def inventory(directory):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}


def samples(protocol):
    return protocol.get('snapshots', protocol.get('pilot_commits', []))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def extract_tar(archive, dest):
    # Git archives contain no required symlinks for these pilot sources. Reject
    # links/devices/traversal rather than trusting arbitrary downloaded archives.
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not target.is_relative_to(dest.resolve()) or not (member.isfile() or member.isdir()):
                raise ValueError(f'Unsafe archive member: {member.name}')
        tar.extractall(dest, filter='data')


def prepare(args):
    protocol = read(args.protocol)
    cache = args.git_cache.resolve()
    output = args.archives.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        run([args.git, 'clone', '--bare', protocol['repository'], cache], output / 'clone.log')
    def git(*argv):
        return subprocess.check_output([args.git, '-C', str(cache), *argv], text=True).strip()
    endpoint = protocol['endpoint_commit']
    # Never use a moving branch as the sampling endpoint.
    history = []
    for line in git('log', '--first-parent', '--format=%H %ct', endpoint).splitlines():
        commit, timestamp = line.split()
        history.append({'commit': commit, 'committer_unix': int(timestamp)})
    roots = git('rev-list', '--max-parents=0', endpoint).splitlines()
    if len(roots) != 1 or history[-1]['commit'] != roots[0]:
        raise RuntimeError('Protocol requires a single root on the chosen lineage')
    cutoff = dt.datetime.fromisoformat(protocol['cutoff_utc'].replace('Z', '+00:00'))
    earliest = dt.datetime.fromtimestamp(history[-1]['committer_unix'], dt.timezone.utc)
    if 'snapshots' in protocol:
        observations = []
        by_commit = {x['commit']: x['committer_unix'] for x in history}
        for item in samples(protocol):
            if item['label'].startswith('creation-'): boundary = earliest
            elif item['label'].startswith('endpoint-'): boundary = cutoff
            else: boundary = dt.datetime(int(item['label']) + 1, 1, 1, tzinfo=dt.timezone.utc)
            observations.append({**item, 'boundary_utc': boundary.isoformat(),
                'commit_date_utc': dt.datetime.fromtimestamp(by_commit[item['commit']], dt.timezone.utc).isoformat()})
    else:
        observations = [{'label': 'root', 'commit': roots[0], 'boundary_utc': earliest.isoformat()}]
        for year in range(earliest.year, cutoff.year + 1):
            for month in (1, 4, 7, 10):
                boundary = dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)
                if earliest < boundary <= cutoff:
                    selected = next(c for c in history if c['committer_unix'] < boundary.timestamp())
                    observations.append({'label': f'{year}-Q{(month - 1) // 3 + 1}', 'boundary_utc': boundary.isoformat(), 'commit': selected['commit']})
        observations.append({'label': 'endpoint', 'commit': endpoint, 'boundary_utc': cutoff.isoformat()})
    archives = []
    for snapshot in samples(protocol):
        destination = output / (snapshot['commit'] + '.tar')
        temporary = destination.with_suffix('.tar.pending')
        archive_spec = protocol.get('archive', {})
        paths = []
        if archive_spec.get('mode') == 'source-and-build-inputs':
            extensions = tuple(x.lower() for x in archive_spec['included_extensions'])
            tree = subprocess.check_output([args.git, '-C', str(cache), 'ls-tree', '-r', '--name-only', snapshot['commit']], text=True).splitlines()
            roots = tuple(snapshot.get('archive_roots', []))
            def build_control(path):
                name = path.rsplit('/', 1)[-1].lower()
                return '/' not in path or name.startswith('directory.build.') or name in ('global.json', 'nuget.config')
            paths = [x for x in tree if x.lower().endswith(extensions) and
                (not roots or x.startswith(roots) or build_control(x))]
            if not paths: raise RuntimeError('Archive allowlist selected no files')
        with temporary.open('wb') as stream:
            subprocess.run([args.git, '-C', str(cache), 'archive', '--format=tar', snapshot['commit'], *paths], stdout=stream, check=True)
        temporary.replace(destination)
        archives.append({**snapshot, 'archive': destination.name, 'sha256': sha(destination)})
    write(output / 'manifest.json', {'protocol_sha256': sha(args.protocol), 'repository': protocol['repository'],
        'endpoint_commit': endpoint, 'history': history, 'observations': observations, 'snapshot_archives': archives})
    print(f'{len(observations)} observations; {len(set(x["commit"] for x in observations))} unique commits; {len(archives)} snapshot archives', flush=True)


def freeze_scanner(root, dotnet):
    frozen = root / 'tool'
    if frozen.exists():
        raise RuntimeError('Refusing to overwrite a frozen tool; choose a new run directory')
    project = frozen / 'source'
    shutil.copytree(HERE / 'Scanner', project, ignore=shutil.ignore_patterns('bin', 'obj'))
    selected = [p for p in (ROOT / 'src/HybridLens.Core').rglob('*.cs') if not {'bin', 'obj'}.intersection(p.parts)]
    for directory in ('Detectors', 'Metrics', 'Abstractions'):
        selected.extend((ROOT / 'src/HybridLens.StaticAnalysis' / directory).glob('*.cs'))
    for src in selected:
        dst = project / 'frozen' / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    # Exact SDK, public feed only; no machine/private NuGet configuration is inherited.
    write(project / 'global.json', {'sdk': {'version': '10.0.203', 'rollForward': 'disable'}})
    (project / 'NuGet.Config').write_text('<?xml version="1.0"?><configuration><packageSources><clear/><add key="nuget.org" value="https://api.nuget.org/v3/index.json"/></packageSources></configuration>\n')
    run([dotnet, 'restore', 'Scanner.csproj', '--configfile', 'NuGet.Config', '--locked-mode'], root / 'logs/scanner-restore.log', cwd=project)
    run([dotnet, 'publish', 'Scanner.csproj', '--no-restore', '-c', 'Release', '-o', frozen / 'app'], root / 'logs/scanner-build.log', cwd=project)
    # Bundle the precise installed runtime, making replay independent of SDK and feeds.
    version = '10.0.11'
    runtime_root = Path(dotnet).resolve().parent
    runtime = frozen / 'runtime'
    (runtime / 'host/fxr').mkdir(parents=True)
    (runtime / 'shared/Microsoft.NETCore.App').mkdir(parents=True)
    shutil.copyfile(dotnet, runtime / 'dotnet.exe')
    shutil.copytree(runtime_root / 'host/fxr' / version, runtime / 'host/fxr' / version)
    shutil.copytree(runtime_root / 'shared/Microsoft.NETCore.App' / version, runtime / 'shared/Microsoft.NETCore.App' / version)
    runtime_config = read(frozen / 'app/Scanner.runtimeconfig.json')
    runtime_config['runtimeOptions']['framework']['version'] = version
    runtime_config['runtimeOptions']['rollForward'] = 'Disable'
    write(frozen / 'app/Scanner.runtimeconfig.json', runtime_config)
    # Keep exact source, dependency lock and binaries; intermediate caches are unnecessary.
    shutil.rmtree(project / 'obj')
    shutil.rmtree(project / 'bin')
    files = inventory(frozen)
    record = {'files': files, 'identity': identity(files), 'sdk': '10.0.203', 'runtime': version, 'roslyn': '4.13.0'}
    write(root / 'tool-manifest.json', record)
    return record


def references(root):
    """Pin public legacy reference packs. Hash both package and extracted files."""
    packages = root / 'reference-packages'
    target = root / 'reference-assemblies'
    records = []
    for name in ('net20', 'net35', 'net40', 'net45', 'net451', 'net452', 'net46', 'net461', 'net462', 'net47', 'net471', 'net472', 'net48'):
        package = f'microsoft.netframework.referenceassemblies.{name}'
        url = f'https://api.nuget.org/v3-flatcontainer/{package}/1.0.3/{package}.1.0.3.nupkg'
        archive = packages / (package + '.1.0.3.nupkg')
        archive.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if member.filename.startswith('build/.NETFramework/') and not member.is_dir():
                    dest = target / Path(member.filename).relative_to('build')
                    if not dest.resolve().is_relative_to(target.resolve()):
                        raise ValueError('Reference package path traversal')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as source, dest.open('wb') as out:
                        shutil.copyfileobj(source, out)
        records.append({'url': url, 'sha256': sha(archive), 'version': '1.0.3'})
    write(root / 'reference-packages.json', {'packages': records, 'files': inventory(target)})
    return target


def project_profile(project, repository, target_override=None):
    props = {}
    inputs = [p / 'Directory.Build.props' for p in reversed(project.parents) if p == repository or repository in p.parents]
    inputs = [p for p in inputs if p.exists()] + [project]
    xml = ET.parse(project).getroot()
    for source in inputs:
     source_xml = ET.parse(source).getroot()
     for node in source_xml.iter():
      tag = node.tag.split('}')[-1]
      if tag in ('TargetFrameworks', 'TargetFramework', 'TargetFrameworkVersion', 'TargetFrameworkProfile', 'ProductVersion'):
       value = (node.text or '').strip()
       if value and '$(' not in value:
        props[tag] = value
    sdk = bool(xml.attrib.get('Sdk'))
    if target_override:
        target = target_override
    elif sdk:
        target = props.get('TargetFrameworks', props.get('TargetFramework', '')).split(';')[0]
        if not target: raise RuntimeError('SDK project has no resolvable target framework')
    elif 'TargetFrameworkVersion' in props:
        target = props['TargetFrameworkVersion']
    elif props.get('ProductVersion', '').startswith('8.'):
        target = 'v2.0'
    else:
        raise RuntimeError('Unrecognised implicit framework: protocol amendment required')
    return {'sdk_style': sdk, 'target': target, 'profile': props.get('TargetFrameworkProfile', '')}


def scanner_command(root):
    return [root / 'tool/runtime/dotnet.exe', root / 'tool/app/Scanner.dll']


def verify_tool(root):
    manifest = read(root / 'tool-manifest.json')
    actual = inventory(root / 'tool')
    if actual != manifest['files'] or identity(actual) != manifest['identity']:
        raise RuntimeError('Frozen tool checksum mismatch')
    return manifest['identity']


def scan_one(root, archive, sample, replica, dotnet, msbuild, reference_root, tool_id):
    label = sample['label']
    work = root / 'work' / replica / label
    bundle = root / 'bundles' / replica / label
    logs = root / 'logs' / replica / label
    work.mkdir(parents=True)
    extract_tar(archive, work)
    protocol = read(root / 'protocol.json')
    project = work / sample.get('project', protocol['scope'].get('project', ''))
    profile = project_profile(project, work, sample.get('target_framework'))
    rsp = work / 'compiler.rsp'
    # Compile is the validity boundary for this static study. Historical projects
    # can have obsolete post-build packaging/copy steps unrelated to C# semantics.
    properties = [('-t:Rebuild' if profile['sdk_style'] else '-t:Compile'), '-p:Configuration=Release', *([f"-p:Platform={sample['platform']}"] if sample.get('platform') else []), '-p:Deterministic=true', '-p:ContinuousIntegrationBuild=true', '-p:DeterministicSourcePaths=false', f'-p:PathMap={work}=/_/', '-p:ProvideCommandLineArgs=true',
        f'-p:CustomAfterMicrosoftCommonTargets={root / "CaptureCompiler.targets"}', f'-p:StudyCapturePath={rsp}',
        '-nologo', '-v:minimal']
    original_sources = {p.relative_to(work).as_posix(): sha(p) for p in work.rglob('*.cs')}
    selectors = []
    if profile['sdk_style']:
        # Historical SourceLink tasks may not load under a later SDK. Repository
        # metadata is not a compiler-semantic input for these detectors.
        if 'Microsoft.SourceLink' in project.read_text(encoding='utf-8-sig'):
            properties += ['-p:EnableSourceControlManagerQueries=false', '-p:EnableSourceLink=false',
                '-p:IncludeSourceRevisionInInformationalVersion=false']
        # A selector is build infrastructure, never an edit to upstream C# source.
        for selector in work.rglob('global.json'):
            old = selector.read_bytes()
            selectors.append((selector, old))
            write(selector, {'sdk': {'version': '10.0.203', 'rollForward': 'disable'}})
        command = [dotnet, 'msbuild', project, '-restore', f'-p:LibraryFrameworks={profile["target"]}', f'-p:TargetFramework={profile["target"]}',
            f'-p:RestoreConfigFile={root / "tool/source/NuGet.Config"}', *properties]
    else:
        package_configs = list(work.rglob('packages.config'))
        restore_command = None
        if package_configs:
            solution_dir = work / sample.get('solution_dir', '')
            restore_command = [msbuild, project, '-t:Restore', '-p:RestorePackagesConfig=true',
                f'-p:SolutionDir={solution_dir}{os.sep}', f'-p:RestoreConfigFile={root / "tool/source/NuGet.Config"}', '-nologo', '-v:minimal']
            run(restore_command, logs / 'restore.log', cwd=work)
        command = [msbuild, project, f'-p:TargetFrameworkVersion={profile["target"]}',
            f'-p:TargetFrameworkRootPath={reference_root}{os.sep}', *properties]
    extra = sample.get('additional_reference_package')
    if extra:
        cache = root / 'compatibility-packages' / extra['sha256']
        archive_path = cache / 'package.nupkg'; extracted = cache / 'content'
        if not archive_path.exists():
            cache.mkdir(parents=True, exist_ok=True); urllib.request.urlretrieve(extra['url'], archive_path)
        if sha(archive_path) != extra['sha256']: raise RuntimeError('Additional reference package checksum mismatch')
        if not extracted.exists():
            extracted.mkdir();
            with zipfile.ZipFile(archive_path) as package:
                package.extractall(extracted)
        command.append(f"-p:ReferencePath={extracted / extra['assembly_directory']}")
    # SDK MSBuild also needs the pinned historical references when its first target is net45.
    if profile['sdk_style'] and profile['target'].startswith('net4'):
        command.append(f'-p:TargetFrameworkRootPath={reference_root}{os.sep}')
    provenance = {**sample, 'replica': replica, 'profile': profile,
        'archive_sha256': sha(archive), 'dependency_restore_command': [str(x) for x in restore_command] if not profile['sdk_style'] and restore_command else None, 'build_command': [str(x) for x in command],
        'sdk_selector_overrides': [{'file': p.relative_to(work).as_posix(), 'original_sha256': hashlib.sha256(b).hexdigest()} for p,b in selectors]}
    write(logs / 'provenance.json', provenance)
    try:
        run(command, logs / 'build.log', cwd=work)
    finally:
        for selector, original in selectors:
            selector.write_bytes(original)
    for rel, original_hash in original_sources.items():
        if sha(work / rel) != original_hash:
            raise RuntimeError('Build modified tracked C# source: ' + rel)
    scan = scanner_command(root)
    scope_prefix = sample.get('production_prefix', protocol['scope'].get('production_prefix', ''))
    run([*scan, 'capture', rsp, project.parent, work, bundle, root / 'protocol.json', tool_id, label, scope_prefix], logs / 'capture.log')
    shutil.copyfile(rsp, bundle / 'compiler.rsp')
    write(bundle / 'provenance.json', provenance)
    output = root / 'measurements' / replica / (label + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    run([*scan, 'replay', bundle, output, tool_id], logs / 'scan.log')
    return {'status': read(output)['status'], 'measurement': output.relative_to(root).as_posix(), 'profile': profile}


def summarise(root):
    state = read(root / 'pilot-status.json')
    rows = []
    comparisons = []
    for sample in samples(read(root / 'protocol.json')):
        label = sample['label']
        a = root / 'measurements/A' / (label + '.json')
        b = root / 'measurements/B' / (label + '.json')
        replay = root / 'measurements/offline' / (label + '.json')
        first = read(a) if a.exists() else None
        second = read(b) if b.exists() else None
        offline = read(replay) if replay.exists() else None
        complete = all(m is not None and m['status'] == 'complete' for m in (first, second, offline))
        equal = complete and first == second == offline
        comparisons.append({'label': label, 'all_complete': complete, 'equal': equal,
            'measurement_sha256': {key: sha(p) if p.exists() else None for key,p in [('A',a),('B',b),('offline',replay)]}})
        row = {'label': label, 'commit': sample['commit'], 'status': first['status'] if first else 'failed',
            'reproducible': equal, 'framework': state['scans'].get('A/' + label, {}).get('profile', {}).get('target')}
        if first:
            row.update(first['counts'])
            row.update(first['denominators'])
            row['obsolete_affected_files'] = first['obsolete_affected_files']
            row.update({key + '_rate': value for key,value in first['rates'].items()})
        rows.append(row)
    gate = all(x['equal'] for x in comparisons)
    write(root / 'comparison.json', {'full_study_gate_passed': gate, 'snapshots': comparisons})
    fields = sorted(set().union(*(r.keys() for r in rows)))
    with (root / 'pilot-summary.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    phase = read(root / 'protocol.json').get('phase', 'study')
    name = read(root / 'protocol.json').get('repository_name', 'Json.NET')
    report = [f'# {name} {phase.replace("-", " " )}', '', f'Full-series gate: {"PASSED" if gate else "NOT PASSED"}.', '',
        f'This series contains {len(rows)} independently reproduced snapshots. Counts do not track individual smell persistence.', '',
        '| Snapshot | Target | Status | God class | Long method | Obsolete symbol/file pairs | Reproduced |',
        '|---|---|---|---:|---:|---:|---|']
    for r in rows:
        report.append(f'| {r["label"]} | {r.get("framework") or "unknown"} | {r["status"]} | {r.get("GodClass", "—")} | {r.get("LongMethod", "—")} | {r.get("ObsoleteApiUsage", "—")} | {r["reproducible"]} |')
    report += ['', 'The frozen protocol, source/reference inventories, compiler arguments, raw findings and compilation errors are retained alongside this report.',
        'Framework transitions change conditional source and API availability; differences cannot be attributed solely to edits in source.', '']
    (root / 'REPORT.md').write_text('\n'.join(report), encoding='utf-8')
    return gate


def pilot(args):
    root = args.output.resolve()
    if root.exists():
        raise RuntimeError('Run directory already exists: use a fresh directory to preserve evidence')
    root.mkdir(parents=True)
    archives = args.archives.resolve()
    manifest = read(archives / 'manifest.json')
    if manifest['protocol_sha256'] != sha(args.protocol):
        raise RuntimeError('Archive manifest belongs to a different protocol')
    shutil.copyfile(args.protocol, root / 'protocol.json')
    for name in ('PROTOCOL.md', 'CaptureCompiler.targets', 'study.py'):
        shutil.copyfile(HERE / name, root / name)
    shutil.copyfile(archives / 'manifest.json', root / 'snapshot-manifest.json')
    # Preserve input archives with the experiment; replay itself needs only bundles/tool.
    (root / 'archives').mkdir()
    for entry in manifest.get('snapshot_archives', manifest.get('pilot_archives', [])):
        original = archives / entry['archive']
        if sha(original) != entry['sha256']:
            raise RuntimeError('Archive checksum mismatch: ' + entry['archive'])
        shutil.copyfile(original, root / 'archives' / entry['archive'])
    tool = freeze_scanner(root, args.dotnet.resolve())
    refs = references(root)
    state = {'scans': {}, 'offline_replays': {}}
    write(root / 'pilot-status.json', state)
    for replica in ('A', 'B'):
        for sample in samples(read(root / 'protocol.json')):
            key = replica + '/' + sample['label']
            print('Scanning ' + key, flush=True)
            try:
                result = scan_one(root, root / 'archives' / (sample['commit'] + '.tar'), sample, replica,
                    args.dotnet.resolve(), args.msbuild.resolve(), refs, tool['identity'])
            except Exception as error:
                result = {'status': 'failed', 'error': str(error)}
                print('  ' + str(error), flush=True)
            state['scans'][key] = result
            write(root / 'pilot-status.json', state)
    replay_all(root)
    print('Pilot gate passed: ' + str(summarise(root)), flush=True)
    seal(root)


def verify_seal(root):
    for rel, expected in read(root / "SHA256SUMS.json").items():
        if sha(root / rel) != expected:
            raise RuntimeError("Checksum mismatch: " + rel)


def replay_verify(root):
    """Re-run sealed bundles without altering the archived experiment."""
    import tempfile
    verify_seal(root)
    tool_id = verify_tool(root)
    with tempfile.TemporaryDirectory(prefix="jsonnet-offline-replay-") as temporary:
        temporary = Path(temporary)
        for sample in samples(read(root / "protocol.json")):
            label = sample["label"]
            output = temporary / (label + ".json")
            run([*scanner_command(root), "replay", root / "bundles/A" / label, output, tool_id], temporary / (label + ".log"))
            expected = root / "measurements/A" / (label + ".json")
            if output.read_bytes() != expected.read_bytes():
                raise RuntimeError("Offline replay differs: " + label)
    print("All five offline replays equal their sealed measurements")


def resume(args):
    """Resume only failed/missing scans in an unsealed run directory."""
    root = args.run.resolve()
    if (root / 'SHA256SUMS.json').exists():
        raise RuntimeError('Refusing to alter a sealed run')
    tool_id = verify_tool(root)
    protocol = read(root / 'protocol.json')
    state = read(root / 'pilot-status.json')
    for replica in ('A', 'B'):
        for sample in samples(protocol):
            key = replica + '/' + sample['label']
            if state['scans'].get(key, {}).get('status') == 'complete':
                continue
            for target in (root / 'work' / replica / sample['label'], root / 'bundles' / replica / sample['label'], root / 'logs' / replica / sample['label']):
                if target.exists(): shutil.rmtree(target)
            measurement = root / 'measurements' / replica / (sample['label'] + '.json')
            if measurement.exists(): measurement.unlink()
            print('Rescanning ' + key, flush=True)
            try:
                result = scan_one(root, root / 'archives' / (sample['commit'] + '.tar'), sample, replica,
                    args.dotnet.resolve(), args.msbuild.resolve(), root / 'reference-assemblies', tool_id)
            except Exception as error:
                result = {'status': 'failed', 'error': str(error)}
            state['scans'][key] = result
            write(root / 'pilot-status.json', state)
    shutil.copyfile(Path(__file__).resolve(), root / 'study.py')
    replay_all(root)
    print('Series gate passed: ' + str(summarise(root)), flush=True)
    seal(root)


def replay_all(root):
    tool_id = verify_tool(root)
    state = read(root / 'pilot-status.json')
    for sample in samples(read(root / 'protocol.json')):
        label = sample['label']
        output = root / 'measurements/offline' / (label + '.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            # No Git, build, package manager, SDK or network command in this path.
            run([*scanner_command(root), 'replay', root / 'bundles/A' / label, output, tool_id], root / 'logs/offline' / (label + '.log'))
            state['offline_replays'][label] = {'status': read(output)['status']}
        except Exception as error:
            state['offline_replays'][label] = {'status': 'failed', 'error': str(error)}
    write(root / 'pilot-status.json', state)


def seal(root):
    # Work trees/build caches are disposable. The manifest seals all durable inputs/results.
    files = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
        if p.is_file() and p.name != 'SHA256SUMS.json' and p.relative_to(root).parts[0] not in ('work', 'logs')}
    write(root / 'SHA256SUMS.json', files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--protocol', type=Path, default=HERE / 'protocol.json'); p.add_argument('--git-cache', type=Path, required=True); p.add_argument('--archives', type=Path, required=True); p.add_argument('--git', default='git')
    p = sub.add_parser('pilot'); p.add_argument('--protocol', type=Path, default=HERE / 'protocol.json'); p.add_argument('--archives', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--dotnet', type=Path, required=True); p.add_argument('--msbuild', type=Path, required=True)
    for command in ('replay', 'report', 'verify'):
        p = sub.add_parser(command); p.add_argument('run', type=Path)
    p = sub.add_parser('resume'); p.add_argument('run', type=Path); p.add_argument('--dotnet', type=Path, required=True); p.add_argument('--msbuild', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare': prepare(args)
    elif args.command == 'pilot': pilot(args)
    elif args.command == 'resume': resume(args)
    elif args.command == 'replay': replay_verify(args.run.resolve())
    elif args.command == 'report':
        verify_seal(args.run.resolve()); summarise(args.run.resolve()); seal(args.run.resolve())
    elif args.command == 'verify':
        verify_seal(args.run.resolve()); print('All sealed files verified')

if __name__ == '__main__':
    main()
