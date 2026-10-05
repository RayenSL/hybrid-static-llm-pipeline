"""Strict, immutable-coordinate line patch contract for the natural cohort."""
import hashlib
import json
from pathlib import Path
import re

FORBIDDEN = ['DllImport','LibraryImport','ModuleInitializer','Process.Start','System.Diagnostics.Process',
 'System.IO.File','System.IO.Directory','Environment.GetEnvironmentVariable','Assembly.Load',
 'Reflection.Emit','HttpClient','WebClient','Socket','System.Net','Console.Open','FileStream',
 'GetEnvironmentVariables','System.Management','Marshal.GetDelegateForFunctionPointer']

def parse(content):
    content=content.strip()
    if content.startswith('```'):
        match=re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```',content,re.S)
        if not match:raise ValueError('Invalid fenced JSON')
        content=match.group(1)
    value=json.loads(content)
    if set(value)!= {'edits'} or not isinstance(value['edits'],list) or not value['edits']:raise ValueError('Expected only a nonempty edits array')
    return value

def apply(source,patch,allowed):
    grouped={}
    for edit in patch['edits']:
        if set(edit)!={'file','start_line','end_line','text'}:raise ValueError('Unexpected edit fields')
        file=edit['file']
        if file not in allowed or '\\' in file or '..' in Path(file).parts:raise ValueError('Outside frozen edit scope')
        start,end=edit['start_line'],edit['end_line']
        if type(start)!=int or type(end)!=int or start<1 or end<start-1:raise ValueError('Invalid coordinates')
        text=edit['text']
        if not isinstance(text,str) or '\x00' in text:raise ValueError('Invalid source text')
        grouped.setdefault(file,[]).append(edit)
    changed=[]
    for file,edits in grouped.items():
        path=source/file;before=path.read_bytes();original=before.decode('utf-8-sig');lines=original.splitlines(keepends=True)
        edits=sorted(edits,key=lambda e:(e['start_line'],e['end_line']))
        for a,b in zip(edits,edits[1:]):
            if b['start_line']<=max(a['start_line'],a['end_line']):raise ValueError('Overlapping/ambiguous edits')
        for edit in reversed(edits):
            start,end=edit['start_line'],edit['end_line']
            if end>len(lines) or start>len(lines)+1:raise ValueError('Edit beyond source')
            replacement=edit['text']
            if replacement and not replacement.endswith('\n'):replacement+='\n'
            lines[start-1:end]=[replacement] if replacement else []
        candidate=''.join(lines)
        for marker in FORBIDDEN:
            if candidate.count(marker)>original.count(marker):raise ValueError('New prohibited runtime capability: '+marker)
        after=candidate.encode('utf-8');path.write_bytes(after)
        changed.append(dict(file=file,before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest(),
           before_bytes=len(before),after_bytes=len(after)))
    return changed
