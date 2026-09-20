"""Metadata-only MindDesk manifest v1 / schema 2 adapter; never opens targets."""
from datetime import datetime, timezone
import json
import uuid


def to_minddesk(snapshot):
    now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    manifest={'format':'minddesk.export.manifest','formatVersion':1,'schemaVersion':2,'exportedAt':now,
              **{key:[] for key in ('workspaces','resources','snippets','canvases','nodes','edges','aliases','todoGroups','todos')}}
    projects={p['id']:p for p in snapshot['projects']}
    tasks={t['id']:t for t in snapshot['tasks']}
    for p in projects.values():
        manifest['workspaces'].append({'id':p['id'],'title':p['title'],'details':p['description'],'createdAt':now,'updatedAt':now,'isPinned':False,'sortIndex':0})
        manifest['canvases'].append({'id':'canvas-'+p['id'],'workspaceId':p['id'],'title':'Workweft tasks','viewportX':0,'viewportY':0,'zoom':1})
    def node(identifier,project,title,body,index):
        return {'id':identifier,'canvasId':'canvas-'+project,'title':title,'body':body,'nodeType':'note',
                'x':(index%4)*320,'y':(index//4)*220,'width':280,'height':160}
    for i,t in enumerate(tasks.values()):
        manifest['todos'].append({'id':t['id'],'workspaceId':t['project_id'],'title':t['title'],'details':t['description'],'isCompleted':False,'isPinned':False,'sortIndex':i})
        manifest['nodes'].append(node(t['id'],t['project_id'],t['title'],t['description'],i))
        for dependency in t['dependencies']:
            manifest['edges'].append({'id':str(uuid.uuid4()),'canvasId':'canvas-'+t['project_id'],'sourceNodeId':dependency,'targetNodeId':t['id'],'label':'dependency','style':'default'})
    for i,a in enumerate(snapshot.get('assets',[])):
        p=tasks[a['task_id']]['project_id']
        manifest['nodes'].append(node('asset-node-'+a['id'],p,a['title'],json.dumps({'schema':'hct.asset.v1','asset':a},ensure_ascii=False),i+len(tasks)))
        if a['kind']=='local_file':
            manifest['resources'].append({'id':a['id'],'workspaceId':p,'title':a['title'],'targetType':'file','displayPath':a['target'],'lastResolvedPath':a['target'],'note':a['description'],'tags':['Workweft'],'scope':'workspace','status':'unavailable'})
    return manifest


def from_minddesk(document):
    if document.get('format')=='minddesk.interchange.package':
        if document.get('formatVersion')!=1:
            raise ValueError('不支持的 MindDesk package 版本')
        document=document['manifest']
    if document.get('format')!='minddesk.export.manifest' or document.get('formatVersion')!=1 or document.get('schemaVersion') not in (1,2):
        raise ValueError('不支持的 MindDesk manifest 版本')
    result={'revision':0,'projects':[],'tasks':[],'assets':[]}
    for p in document['workspaces']:
        result['projects'].append({'id':p['id'],'title':p['title'],'description':p['details'],'archived':False})
    for t in document.get('todos',[]):
        result['tasks'].append({'id':t['id'],'project_id':t['workspaceId'],'title':t['title'],'description':t['details'],'status':'todo','dependencies':[]})
    tasks={t['id']:t for t in result['tasks']}
    canvases={c['id']:c['workspaceId'] for c in document['canvases']}
    for n in document['nodes']:
        if n['nodeType']!='note':
            continue
        try:
            body=json.loads(n['body'])
        except (ValueError,TypeError):
            body=None
        if isinstance(body,dict) and body.get('schema')=='hct.asset.v1':
            result['assets'].append(body['asset'])
        elif n['id'] not in tasks:
            task={'id':n['id'],'project_id':canvases[n['canvasId']],'title':n['title'],'description':n['body'],'status':'todo','dependencies':[]}
            result['tasks'].append(task)
            tasks[task['id']]=task
    for edge in document['edges']:
        if edge.get('label')=='dependency' and edge['sourceNodeId'] in tasks and edge['targetNodeId'] in tasks:
            tasks[edge['targetNodeId']]['dependencies'].append(edge['sourceNodeId'])
    existing={a['id'] for a in result['assets']}
    for resource in document['resources']:
        if resource['id'] in existing:
            continue
        project=resource.get('workspaceId') or 'minddesk-global-library'
        if project=='minddesk-global-library' and not any(p['id']==project for p in result['projects']):
            result['projects'].append({'id':project,'title':'MindDesk Global Library','description':'导入的全局资源引用','archived':False})
        task_id='resource-task-'+project
        if task_id not in tasks:
            task={'id':task_id,'project_id':project,'title':'MindDesk 资源','description':'只登记资源位置，不读取内容','status':'todo','dependencies':[]}
            result['tasks'].append(task)
            tasks[task_id]=task
        result['assets'].append({'id':resource['id'],'task_id':task_id,'title':resource['title'],'kind':'local_file','target':resource['displayPath'],'description':resource['note']})
    return result


def import_snapshot(document):
    if not isinstance(document,dict):
        raise ValueError('需要 JSON 对象')
    if document.get('format') in ('minddesk.export.manifest','minddesk.interchange.package'):
        return from_minddesk(document)
    if document.get('schema')!='HCTWorkspaceExportV1':
        raise ValueError('不支持的导入格式')
    snapshot=document['snapshot']
    if snapshot.get('schema_version') not in (1,2,3,4):
        raise ValueError('不支持的快照版本')
    return snapshot
