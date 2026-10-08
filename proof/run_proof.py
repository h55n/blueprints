import urllib.request,urllib.error,base64,json,pathlib,time,os
base='http://127.0.0.1:18080/api/v1'
auth=base64.b64encode(('proof@local.invalid:'+os.environ['PROOF_PASSWORD']).encode()).decode()
out=pathlib.Path('evidence');out.mkdir(exist_ok=True)
def call(path,method='GET',body=None,ctype='application/json'):
    r=urllib.request.Request(base+path,data=body,method=method,headers={'Authorization':'Basic '+auth,'Content-Type':ctype})
    with urllib.request.urlopen(r,timeout=15) as response:return response.read()
for _ in range(120):
    try:call('/configs');break
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):raise RuntimeError('Kestra rejected proof credentials') from exc
        time.sleep(2)
    except (urllib.error.URLError,TimeoutError,ConnectionError):time.sleep(2)
else:raise RuntimeError('Kestra did not become ready')
blueprint=pathlib.Path('flows/scheduled-markdown-link-audit.yaml').read_text()
import re;ext=blueprint.split('\nextend:\n')[1];md=re.search(r'^  metaDescription: (.+)$',ext,re.M).group(1);assert len(md)<=160 and '\n  ee: false' in ext and '\n  demo: false' in ext
flow=blueprint.split('\nextend:\n')[0].encode()+b'\n'
try:call('/flows','POST',flow,'application/x-yaml')
except urllib.error.HTTPError as exc:raise RuntimeError(exc.read().decode()[:2000]) from exc
def run(inputs):
    boundary='kestra-proof-boundary'
    data=''.join('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n' for key,value in inputs.items())+'--'+boundary+'--\r\n'
    e=json.loads(call('/executions/company.team/scheduled-markdown-link-audit','POST',data.encode(),'multipart/form-data; boundary='+boundary))
    for _ in range(180):
        e=json.loads(call('/executions/'+e['id']))
        if e['state']['current'] in ('SUCCESS','FAILED','WARNING','KILLED'):return e
        time.sleep(1)
    raise RuntimeError('Execution did not finish')
e=run({});assert e['state']['current']=='SUCCESS',e
out.joinpath('execution.json').write_text(json.dumps(e,indent=2))
outputs=json.loads(call('/main/outputs/executions/'+e['id']));out.joinpath('outputs.json').write_text(json.dumps(outputs,indent=2))
from urllib.parse import urlencode
for key,filename in [('report_json','report.json'),('report_markdown','report.md')]:
    out.joinpath(filename).write_bytes(call('/executions/'+e['id']+'/file?'+urlencode({'path':outputs[key]})))
out.joinpath('execution-logs.json').write_bytes(call('/logs/'+e['id']))
report=json.loads(out.joinpath('report.json').read_text());assert report['checked']>0 and report['successful']>0,report
assert all('403' not in x['status'] and '429' not in x['status'] for x in report['needs_fix'])
negatives=[]
for name,inputs in [('local-url',{'repository':'file:///tmp/fixture'}),('other-host',{'repository':'https://example.org/test/repo'}),('credential-url',{'repository':'https://user:dummy@github.com/test/repo'}),('empty-scope',{'markdown_glob':'no-match-proof*.md'})]:
    d=run(inputs);assert d['state']['current']=='FAILED',d
    ids=[t['taskId'] for t in d['taskRunList']]
    assert ('clone' not in ids) if name!='empty-scope' else ('report' not in ids)
    negatives.append({'name':name,'id':d['id'],'state':d['state']['current'],'tasks':ids})
    logs=json.loads(call('/logs/'+d['id']));out.joinpath('negative-logs-'+name+'.json').write_text(json.dumps(logs,indent=2))
    assert not [l for l in logs if l.get('level')=='ERROR' and l.get('taskId') is None],name
    print('NEGATIVE',name,[(l.get('level'),l.get('taskId'),str(l.get('message'))[:200]) for l in logs if l.get('level') in ('ERROR','WARN')])
out.joinpath('negative-executions.json').write_text(json.dumps(negatives,indent=2))
print('Actual Dockerized Kestra execution SUCCESS:',e['id']);print('Four actual negative executions PASS');print(json.dumps(report,indent=2))
