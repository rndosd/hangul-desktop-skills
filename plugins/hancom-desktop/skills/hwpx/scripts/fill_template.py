"""Fill registered blank templates through the existing atomic batch editor."""
from pathlib import Path
import hashlib
import json
import os
from candidate_runtime import activate
from select_document_block import BlockLibrary, FileRef, decode_json

SCHEMA = 'hangul.fill.v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _read_ref(root, spec, role):
    ref = FileRef.parse(spec, role)
    path = ref.resolve(root, role)
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == ref.sha256, 'changed ' + role)
    return path, data


def load_form(catalog, template_id):
    library = BlockLibrary(Path(catalog))
    selected = library.select(template_id)
    card = selected['block']
    require('fill' in card, 'This block has no prepared input bindings.')
    manifest_path, raw = _read_ref(library.root, card['fill'], 'fill')
    manifest = decode_json(raw, 'FILL')
    require(manifest.get('schema') == SCHEMA and manifest.get('blockId') == template_id, 'fill manifest identity mismatch')
    require(manifest.get('sourceDocumentSha256') == selected['files']['document']['sha256'], 'changed source excerpt')
    template, data = _read_ref(library.root, manifest['template'], 'template')
    styles_path, raw_styles = _read_ref(library.root, manifest['styles'], 'styles')
    styles = decode_json(raw_styles, 'STYLES')
    refs = dict(selected['files'])
    refs.update(fill={'path':str(manifest_path),'sha256':hashlib.sha256(raw).hexdigest()},
                template={'path':str(template),'sha256':hashlib.sha256(data).hexdigest()},
                styles={'path':str(styles_path),'sha256':hashlib.sha256(raw_styles).hexdigest()},
                catalog={'path':str(library.catalog),'sha256':hashlib.sha256(library.catalog.read_bytes()).hexdigest()})
    if isinstance(manifest.get('verification'),dict):
        verification=manifest['verification']
        proof_path,proof_raw=_read_ref(library.root,verification['evidence'],'prepared evidence')
        proof=decode_json(proof_raw,'PREPARED EVIDENCE')
        require(proof.get('outcome')=='PASS_SAMPLE' and proof.get('templateSha256')==manifest['template']['sha256'],'prepared evidence mismatch')
        refs['preparedEvidence']={'path':str(proof_path),'sha256':hashlib.sha256(proof_raw).hexdigest()}
    if manifest.get('preview'):
        preview_path,preview_raw=_read_ref(library.root,manifest['preview'],'prepared preview')
        refs['preparedPreview']={'path':str(preview_path),'sha256':hashlib.sha256(preview_raw).hexdigest()}
    return manifest, template, styles, refs


def describe(catalog, template_id):
    manifest, template, styles, refs = load_form(catalog, template_id)
    return {'status':'PREPARED_FORM', 'template':template_id,
            'slots':{key:{'label':value.get('label',key),'role':value['role'],**({'contentOnly':True} if value.get('property')=='caption' else {})} for key,value in manifest['slots'].items() if 'valueFrom' not in value},
            **({'linkedPlacements':{key:value['valueFrom'] for key,value in manifest['slots'].items() if 'valueFrom' in value}} if any('valueFrom' in value for value in manifest['slots'].values()) else {}),
            'repeats':{key:{'label':value.get('label',key),'fields':list(value['fields'])} for key,value in manifest.get('repeats',{}).items()},
            'roles':list(styles), 'preview':refs.get('preparedPreview'), 'preparedVerification':manifest.get('verification'),
            'preparation':manifest.get('preparation',{'mode':'prepared-source-design'}), 'limits':manifest.get('limits',[]),
            'native':'NOT_CHECKED', 'values':'Scalar strings and arrays of records. Omitted inputs stay blank or retain generic labels.'}


def _value(value):
    require(isinstance(value,str) and not any(c in value for c in '\r\n\t'), 'Use single-paragraph strings; use repeat items for separate paragraphs.')
    return value


def compile_fill(manifest, source, output, values, styles, overrides=None):
    activate()
    from hwpx_automation.office.agent.document import HwpxAgentDocument
    from layout_task import role_properties
    require(isinstance(values,dict), 'values must be an object')
    slots, repeats = manifest['slots'], manifest.get('repeats',{})
    require(not set(slots) & set(repeats), 'duplicate slot/repeat name')
    aliases={name:binding['valueFrom'] for name,binding in slots.items() if 'valueFrom' in binding}
    for name,target in aliases.items():
        require(isinstance(target,str) and target in slots and target not in aliases,'linked placement requires a canonical fixed input: '+name)
    inputs=set(slots)-set(aliases)
    require(not set(values) - inputs - set(repeats), 'unknown input name: ' + ', '.join(set(values)-inputs-set(repeats)))
    styles = {key:dict(value) for key,value in styles.items()}
    prepared_styles = manifest.get('preparedStylesSha256') == manifest['styles']['sha256']
    if overrides is not None:
        require(isinstance(overrides,dict) and set(overrides)<=set(styles), 'unknown style role')
        for role,changes in overrides.items():
            require(isinstance(changes,dict), 'role override must be an object')
            styles[role].update(changes)
    with HwpxAgentDocument.open(source) as view:
        require(view.revision == 'sha256:'+manifest['template']['sha256'], 'stale prepared template')
        records={record.path:record for record in view.records}
        order={record.path:index for index,record in enumerate(view.records)}
        owners={}
        commands=[]
        def command(op, **arguments):
            identity='fill-'+str(len(commands)+1)
            commands.append(dict(commandId=identity,op=op,**arguments))
            return identity
        def qualify(binding, owner):
            require(isinstance(binding,dict) and binding.get('role') in styles, 'unknown binding role')
            path=binding['path']
            allowed_kind = 'table' if binding.get('property') == 'caption' else 'run'
            require(binding.get('property','text') in ('text','caption'), 'unknown slot property')
            require(path in records and records[path].kind==allowed_kind, 'slot must bind its declared text or caption target: '+path)
            require(path not in owners, 'overlapping input bindings: '+path)
            owners[path]=owner
            require(isinstance(binding.get('prefix',''),str) and isinstance(binding.get('suffix',''),str), 'invalid slot affix')
            return records[path]
        for name,binding in slots.items():qualify(binding,name)
        prototypes=[]
        for name,repeat in repeats.items():
            prototype=records.get(repeat['path'])
            require(prototype is not None and prototype.kind in ('row','paragraph'), 'repeat requires a row or paragraph')
            if prototype.kind=='row':
                require(not any(c.span[0]>1 for row in prototype.native.table.rows for c in row.cells), 'repeat table has vertical merges')
            for binding in repeat['fields'].values():
                require(not binding.get('marker') and binding.get('property','text')=='text', 'scoped markers and captions support fixed slots only')
                record=qualify(binding,name)
                require(record.path.startswith(prototype.path+'/'), 'repeat input outside its prototype')
            prototypes.append((name,prototype))
        for name,prototype in prototypes:
            require(not any(path.startswith(prototype.path+'/') and owner!=name for path,owner in owners.items()), 'overlapping fixed/repeated input')
            require(not any(other.path.startswith(prototype.path+'/') for other_name,other in prototypes if other_name!=name), 'nested repeats unsupported')

        def add_binding(pending,binding,value,include_style=True):
            record=records[binding['path']]
            text=binding.get('prefix','')+_value(value)+binding.get('suffix','')
            if binding.get('property') == 'caption':
                pending.setdefault(record.path,{})['caption']=text
                return
            wanted=role_properties(styles[binding['role']]) if include_style and (not prepared_styles or overrides) else {'run':{}}
            if binding.get('marker'):
                wanted['run']=dict(wanted['run'],textReplacement={'search':binding['marker'],'replacement':text})
            else:
                wanted['run']=dict(wanted['run'],text=text)
            while record is not None and record.kind not in ('table','section','document'):
                props=wanted.get(record.kind,{})
                if props:
                    existing=pending.setdefault(record.path,{})
                    for prop,value in props.items():
                        require(prop not in existing or existing[prop]==value, 'conflicting styles for '+record.path+'.'+prop)
                        existing[prop]=value
                record=records.get(record.parent_path)

        def emit(pending):
            for path,props in pending.items():command('set',path=path,properties=props)

        pending={}
        for name,binding in slots.items():
            canonical_name=aliases.get(name,name)
            add_binding(pending,binding,values.get(canonical_name,slots[canonical_name].get('default','')))
        emit(pending)
        for name,prototype in sorted(prototypes,key=lambda item:order[item[1].path],reverse=True):
            repeat=repeats[name]
            items=values.get(name,[])
            require(isinstance(items,list) and len(items)<=100,'repeat requires at most 100 items')
            if not items:
                command('remove',path=prototype.path)
                continue
            styled=False
            def fill_donor(item):
                nonlocal styled
                require(isinstance(item,dict) and set(item)<=set(repeat['fields']), 'unknown repeat input for '+name)
                pending={}
                for key,binding in repeat['fields'].items():add_binding(pending,binding,item.get(key,''),include_style=not styled)
                emit(pending)
                styled=True
            cursor=prototype.path
            for item in items[1:]:
                fill_donor(item)
                identity=command('copy',path=prototype.path,parent=prototype.parent_path,position={'mode':'after','path':cursor})
                cursor='$'+identity+'.path'
            fill_donor(items[0])
        require(commands, 'no form content or repeat edits')
        plan={'schemaVersion':'hwpx.agent-batch/v1','input':{'filename':str(source)},'output':{'filename':str(output),'overwrite':False},
              'commands':commands,'expectedRevision':view.revision,'idempotencyKey':'fill-'+hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24],
              'dryRun':False,'quality':'transparent','verificationRequirements':['package','reopen','openSafety','semanticDiff','bytePreservation']}
        return plan


def fill(catalog, template_id, output, values, *, styles=None, dry_run=False):
    from hangul_task import batch, stage_directory, sha
    manifest,source,defaults,refs=load_form(catalog,template_id)
    output=Path(output).absolute()
    require(output.suffix.lower()=='.hwpx' and output.parent.is_dir() and not output.exists() and not output.is_symlink(), 'new .hwpx output required')
    with stage_directory(output.parent) as folder:
        candidate=Path(folder)/'stage-0.hwpx'
        plan=compile_fill(manifest,source,candidate,values,defaults,styles)
        from hwpx_automation.office.agent.model import MAX_COMMANDS
        commands=plan['commands']
        batches=1
        if len(commands) <= MAX_COMMANDS:
            result=batch(plan,dry_run=dry_run)
        else:
            require(all(c['op']=='set' and not c['path'].startswith('$') for c in commands), 'This repeat exceeds the bounded batch size; reduce the repeat items.')
            stages=[]
            for offset in range(0,len(commands),MAX_COMMANDS):
                next_candidate=Path(folder)/f'stage-{offset//MAX_COMMANDS}.hwpx'
                step=dict(plan,commands=commands[offset:offset+MAX_COMMANDS],output={'filename':str(next_candidate),'overwrite':False},
                          idempotencyKey=plan['idempotencyKey']+f'-{offset}')
                if stages:
                    step['input']={'filename':str(candidate)}
                    step['expectedRevision']=stages[-1]['documentRevision']
                result=batch(step,dry_run=False)
                stages.append(result)
                candidate=next_candidate
                if not result.get('ok'):break
            batches=len(stages)
            result=dict(result,dryRun=dry_run,stages=stages)
        result['output']={'filename':str(output)}
        result['documentPublished']=False
        pipeline=result.get('verificationReport',{}).get('savePipeline')
        if pipeline is not None:pipeline['outputPath']=None
        if result.get('ok'):
            for ref in refs.values():require(sha(ref['path'])==ref['sha256'], 'form provenance changed during fill: '+ref['path'])
            if not dry_run:
                require(candidate.is_file() and 'sha256:'+sha(candidate)==result['documentRevision'],'candidate digest mismatch')
                os.link(candidate,output)
                result['documentPublished']=True
                if pipeline is not None:pipeline['outputPath']=str(output)
        result['form']={'template':template_id,'inputs':len(values),'commands':len(plan['commands']),'mutationBatches':batches}
        return result
