"""Conservative Python source-semantic adapter; does not import target modules.

Only unambiguous source bindings are resolved. Dynamic receivers and syntax outside
CPython's grammar remain explicit gaps, never zero-valued semantic measurements.
"""
import ast,builtins,hashlib,re,warnings
warnings.filterwarnings("ignore",category=SyntaxWarning)
from collections import defaultdict
BOUNDARIES=(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda)
def descendants(node):
    for child in ast.iter_child_nodes(node):
        if isinstance(child,BOUNDARIES):continue
        yield child;yield from descendants(child)
def dotted(n):
    if isinstance(n,ast.Name):return n.id
    if isinstance(n,ast.Attribute):
        base=dotted(n.value);return base+'.'+n.attr if base else None
    return None
_LEGACY_TOOL=None
def legacy_tool():
    global _LEGACY_TOOL
    if _LEGACY_TOOL is None:
        from lib2to3.refactor import RefactoringTool,get_fixers_from_package
        syntax_fixers=('print','except','raise','exec','repr','numliterals','ne')
        _LEGACY_TOOL=RefactoringTool(['lib2to3.fixes.fix_'+name for name in syntax_fixers])
    return _LEGACY_TOOL
def normalise_indentation(text):
    lines=[]
    for line in text.splitlines(keepends=True):
        width=len(line)-len(line.lstrip(' \t'));indent=line[:width]
        line=line.replace('\r\n','\n').replace('\r','\n')
        lines.append(indent.expandtabs(8)+line[width:])
    text=''.join(lines)
    text=re.sub(r'''^(\s*raise\s+(["'][^"']*["']))\s*,''',r'\1 from',text,flags=re.M)
    text=re.sub(r'^(\s*raise\s+[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*,\s*[\\]\r?\n(\s*)([^\n]+)',r'\1(\n\2\3)',text,flags=re.M)
    text=re.sub(r'\blambda\s*\([^():]*,[^():]*\)\s*:',r'lambda __legacy_tuple:',text)
    text=re.sub(r'^(\s*except\s+[^,\n]+),\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\s*:',r'\1 as __legacy_exception:',text,flags=re.M)
    text=re.sub(r'^(\s*except\s+[^,\n]+),\s*\(([^,\s)]+)[^)]*\)\s*:',r'\1 as \2:',text,flags=re.M)
    text=re.sub(r'^(\s*)True\s*,\s*False\s*=',r'\1__legacy_true, __legacy_false =',text,flags=re.M)
    text=re.sub(r'''\bur(?=["'])''','r',text,flags=re.I)
    text=re.sub(r'\basync\b','__legacy_async',text)
    return text
def parse_source(data,path):
    """Parse current Python, falling back to a line-preserving Python 2 conversion."""
    try:return ast.parse(data,filename=path),'cpython'
    except SyntaxError as original:
        try:
            if isinstance(data,bytes):
                import io,tokenize
                encoding,_=tokenize.detect_encoding(io.BytesIO(data).readline);text=data.decode(encoding)
            else:text=data
            text=normalise_indentation(text)
            parse_text=text if text.endswith('\n') else text+'\n'
            converted=str(legacy_tool().refactor_string(parse_text,path))
            if len(converted.splitlines())!=len(text.splitlines()):raise SyntaxError('conversion changed source line count')
            return ast.parse(converted,filename=path),'lib2to3-line-preserving'
        except Exception:raise original
def analyse(sources,complexities):
    modules={};errors=[];symbols={};classes={};imports={};deprecations={};bound_names={};parse_modes={}
    for path,data in sorted(sources.items()):
        module=path[:-3].replace('/','.');module=module.removesuffix('.__init__')
        try:tree,parse_modes[path]=parse_source(data,path)
        except (SyntaxError,UnicodeError) as e:errors.append({'path':path,'line':getattr(e,'lineno',1),'reason':'unsupported_python_syntax'});continue
        modules[module]=(path,tree);bindings={};counts=defaultdict(int)
        for n in tree.body:
            if isinstance(n,ast.Import):
                for a in n.names:bindings[a.asname or a.name.split('.')[0]]=a.name if a.asname else a.name.split('.')[0];counts[a.asname or a.name.split('.')[0]]+=1
            elif isinstance(n,ast.ImportFrom):
                base=n.module or ''
                if n.level:
                    package=module if path.endswith('/__init__.py') else module.rpartition('.')[0]
                    parts=package.split('.');base='.'.join(parts[:len(parts)-n.level+1]+([base] if base else []))
                for a in n.names:
                    if a.name!='*':bindings[a.asname or a.name]=base+'.'+a.name;counts[a.asname or a.name]+=1
            elif isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                bindings[n.name]=module+'.'+n.name;counts[n.name]+=1
            elif isinstance(n,(ast.Assign,ast.AnnAssign)):
                for target in (n.targets if isinstance(n,ast.Assign) else [n.target]):
                    for x in ast.walk(target):
                        if isinstance(x,ast.Name):counts[x.id]+=1
        imports[module]={k:v for k,v in bindings.items() if counts[k]==1};bound_names[module]=set(counts)
        for n in tree.body:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                key=module+'.'+n.name
                if counts[n.name]!=1:continue
                symbols[key]=(module,path,n)
                if isinstance(n,ast.ClassDef):
                    classes[key]={'node':n,'module':module,'path':path,'methods':{x.name:x for x in n.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef))},'fields':set(),'instance_fields':set(),'bases':[]}
                    for x in n.body:
                        if isinstance(x,(ast.Assign,ast.AnnAssign)):
                            for target in (x.targets if isinstance(x,ast.Assign) else [x.target]):
                                if isinstance(target,ast.Name):classes[key]['fields'].add(target.id)
                    for name,method in classes[key]['methods'].items():
                        symbols[key+'.'+name]=(module,path,method)
                        for x in descendants(method):
                            if isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=='self' and isinstance(x.ctx,ast.Store):classes[key]['fields'].add(x.attr);classes[key]['instance_fields'].add(x.attr)
    def resolve_name(node,module,shadow=frozenset()):
        name=dotted(node)
        if not name:return None
        head,*tail=name.split('.')
        if head in shadow:return None
        binding=imports[module].get(head)
        return '.'.join([binding]+tail) if binding else None
    for key,c in classes.items():
        c['bases']=[resolve_name(n,c['module']) for n in c['node'].bases]
    def ancestry(key,seen=None):
        seen=set() if seen is None else set(seen)
        if key in seen:return seen
        seen.add(key)
        for base in classes.get(key,{}).get('bases',[]):
            if base in classes:seen|=ancestry(base,seen)
        return seen
    def field_owner(key,field):
        if key not in classes:return None
        if field in classes[key]['fields']:return key
        for base in classes[key]['bases']:
            if base in classes and base!=key and field in classes[base]['fields']:return base
        return None
    # PEP 702 markers are resolved through imports, not matched by a bare decorator name.
    for key,(module,path,n) in symbols.items():
        markers=[]
        for decorator in n.decorator_list:
            target=decorator.func if isinstance(decorator,ast.Call) else decorator
            if resolve_name(target,module) in {'warnings.deprecated','typing_extensions.deprecated'}:
                markers.append({'kind':'pep702_decorator','line':decorator.lineno})
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            shadow={a.arg for a in [*n.args.posonlyargs,*n.args.args,*n.args.kwonlyargs]}
            for child in descendants(n):
                if isinstance(child,ast.Name) and isinstance(child.ctx,(ast.Store,ast.Del)):shadow.add(child.id)
            for statement in n.body:
                if not isinstance(statement,ast.Expr) or not isinstance(statement.value,ast.Call):continue
                call=statement.value
                category=call.args[1] if len(call.args)>1 else next((k.value for k in call.keywords if k.arg=='category'),None)
                if resolve_name(call.func,module,shadow)=='warnings.warn' and isinstance(category,ast.Name) and category.id=='DeprecationWarning' and category.id not in shadow and category.id not in bound_names[module]:
                    markers.append({'kind':'unconditional_deprecation_warning','line':call.lineno})
        if markers:deprecations[key]=markers
    class_records=[];uses={};unresolved_uses=[];source_references=set()
    # Top-level references and declared methods/functions only; nested scopes have independent bindings.
    for key,(module,path,n) in symbols.items():
        if isinstance(n,ast.ClassDef):continue
        classkey=key.rpartition('.')[0] if key.rpartition('.')[0] in classes else None
        args=list(n.args.posonlyargs)+list(n.args.args)+list(n.args.kwonlyargs)
        if n.args.vararg:args.append(n.args.vararg)
        if n.args.kwarg:args.append(n.args.kwarg)
        shadow={a.arg for a in args};assigned=defaultdict(list)
        for x in descendants(n):
            if isinstance(x,ast.Name) and isinstance(x.ctx,(ast.Store,ast.Del)):shadow.add(x.id)
            if isinstance(x,ast.Assign) and len(x.targets)==1 and isinstance(x.targets[0],ast.Name):assigned[x.targets[0].id].append(x.value)
            if isinstance(x,(ast.Import,ast.ImportFrom)):
                shadow.update(a.asname or a.name.split('.')[0] for a in x.names)
        types={a.arg:resolve_name(a.annotation,module) for a in args if a.annotation is not None}
        if classkey and args and args[0].arg=='self':types['self']=classkey
        for name,values in assigned.items():
            if len(values)==1 and isinstance(values[0],ast.Call):types[name]=resolve_name(values[0].func,module,shadow)
            else:types.pop(name,None)
        own=set();foreign=set();unknown=[]
        for x in descendants(n):
            if isinstance(x,ast.Attribute):
                receiver=types.get(x.value.id) if isinstance(x.value,ast.Name) else None
                receiver=receiver or resolve_name(x.value,module,shadow)
                owner=field_owner(receiver,x.attr)
                if owner:
                    if classkey==owner and isinstance(x.value,ast.Name) and x.value.id=='self' and x.attr in classes[classkey]['instance_fields']:own.add(x.attr)
                    elif classkey and owner not in ancestry(classkey):foreign.add(owner+'.'+x.attr)
                elif receiver in classes and x.attr in classes[receiver]['methods']:pass
                elif resolve_name(x,module,shadow) in symbols:pass
                else:unknown.append({'line':x.lineno,'reason':'unresolved_attribute','expression':dotted(x)})
            if isinstance(x,ast.Call):
                target=resolve_name(x.func,module,shadow)
                if isinstance(x.func,ast.Attribute) and isinstance(x.func.value,ast.Name):
                    receiver=types.get(x.func.value.id)
                    if receiver in classes:target=receiver+'.'+x.func.attr
                if target in symbols:
                    source_references.add((path,target))
                    owner=target.rpartition('.')[0];origin=target if target in deprecations else owner if owner in deprecations and owner!=classkey else None
                    if origin:
                        identity=(path,target)
                        uses.setdefault(identity,{'path':path,'line':x.lineno,'symbol':target,'declaration_path':symbols[origin][1],'deprecation_origin':origin,'markers':deprecations[origin]})
                elif not (isinstance(x.func,ast.Name) and x.func.id in vars(builtins) and x.func.id not in shadow):unresolved_uses.append({'path':path,'line':x.lineno,'reason':'unresolved_call'})
        if classkey:
            classes[classkey].setdefault('method_metrics',{})[n.name]={'own':own,'foreign':foreign,'unresolved':unknown}
    for key,c in classes.items():
        ms=c['methods'];metrics=c.get('method_metrics',{});wmc=sum(complexities.get((c['path'],m.lineno),1) for name,m in ms.items() if name not in {'__init__','__new__'})
        public=[name for name in ms if not name.startswith('_')];pairs=[(a,b) for i,a in enumerate(public) for b in public[i+1:]]
        connected=sum(bool(metrics.get(a,{}).get('own',set()) & metrics.get(b,{}).get('own',set())) for a,b in pairs)
        tcc=connected/len(pairs) if pairs else 1.0;foreign=set().union(*(m['foreign'] for m in metrics.values())) if metrics else set()
        unknown=[v for m in metrics.values() for v in m['unresolved']]
        if c['node'].decorator_list or c['node'].keywords or any(m.decorator_list for m in ms.values()):unknown.append({'reason':'decorator_or_metaclass_semantics'})
        for member in c['node'].body:
            if isinstance(member,(ast.Assign,ast.AnnAssign)) and any(isinstance(x,(ast.Call,ast.Attribute)) for x in ast.walk(member)):unknown.append({'reason':'class_initialiser_or_descriptor_semantics'})
        if any(b not in classes for b in c['bases']):unknown.append({'reason':'unresolved_base_class'})
        if any(name in ms for name in ['__getattr__','__getattribute__','__setattr__']):unknown.append({'reason':'dynamic_attribute_protocol'})
        class_records.append({'path':c['path'],'line':c['node'].lineno,'symbol':key,'wmc':wmc,'wmc_complete':all((c['path'],m.lineno) in complexities for name,m in ms.items() if name not in {'__init__','__new__'}),'atfd':len(foreign),'tcc':tcc,'public_methods':len(public),'foreign_attributes':sorted(foreign),'unresolved_count':len(unknown),'unresolved_examples':unknown[:5]})
    return {'classes':class_records,'obsolete':list(uses.values()),'diagnostics':errors,'unresolved_references':unresolved_uses,'source_api_references':len(source_references),'declarations':len(symbols),'deprecation_markers':len(deprecations),'parse_modes':dict(sorted(parse_modes.items()))}
