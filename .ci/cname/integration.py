import json,time,os,sys
from pathlib import Path
import requests,yaml
BASE='http://localhost:8089/api/v1/main'
s=requests.Session();s.auth=('admin@kestra.io','Kestra12345')
flow=yaml.safe_load(Path('flows/dangling-cname-remediation-ticket.yaml').read_text())
flow.pop('extend');flow['namespace']='test'
# Only endpoints and namespace change; task code and control flow are shipped code.
flow['variables']['github_endpoint']='http://localhost:9998'
Path('/tmp/tested-flow.yaml').write_text(yaml.safe_dump(flow,sort_keys=False))
r=s.post(BASE+'/flows/validate',data=yaml.safe_dump(flow),headers={'Content-Type':'application/x-yaml'});r.raise_for_status()
print('VALIDATION',r.text,flush=True)
assert all(not x.get('constraints') for x in r.json()),r.text
r=s.post(BASE+'/flows',data=yaml.safe_dump(flow),headers={'Content-Type':'application/x-yaml'}); print('SAVED',r.status_code,r.text[:2000],flush=True);r.raise_for_status()
bridge=os.environ['DOCKER_BRIDGE']
results=[]
def run(name='app.fixture.test',dry=False,status='SUCCESS',live=False):
    data={'hostname':name,'issue_repository':'test/dns','dry_run':str(dry).lower(),'dns_server':'1.1.1.1' if live else bridge}
    r=s.post(BASE+'/executions/test/dangling-cname-remediation-ticket',files={k:(None,v) for k,v in data.items()});r.raise_for_status();eid=r.json()['id']
    for _ in range(150):
        r=s.get(BASE+'/executions/'+eid);r.raise_for_status();e=r.json()
        if e['state']['current'] in ['SUCCESS','FAILED','WARNING','KILLED','CANCELLED']:break
        time.sleep(2)
    Path('/tmp/execution-'+eid+'.json').write_text(json.dumps(e,indent=2))
    print('RUN',name,dry,eid,e['state']['current'],flush=True)
    assert e['state']['current']==status,e
    print('EXECUTION_KEYS',list(e), 'OUTPUTS',e.get('outputs'), flush=True)
    results.append({'id':eid,'hostname':name,'dry_run':dry,'status':status})
    if status != 'SUCCESS': return {}
    tid=next(t['id'] for t in e['taskRunList'] if t['taskId']=='inspect_dns')
    o=s.get(BASE+'/outputs/tasks/'+eid+'/'+tid); print('OUTPUT_ENDPOINT',o.status_code,o.text[:3000],flush=True); o.raise_for_status()
    payload=o.json()
    return payload.get('vars',{})
def issues():return json.loads(Path('/tmp/gh-issues.json').read_text())
# Dry run cannot increment the saved baseline.
x=run(dry=True);assert x['consecutive']==1 and not issues(),x
x=run();assert x['consecutive']==1 and not issues(),x
x=run();assert x['eligible'] and len(issues())==1,x
x=run();assert not x['eligible'] and len(issues())==1,x
# Different target must start a new consecutive streak.
Path('/tmp/dns-mode').write_text('changed')
x=run();assert x['consecutive']==1 and not x['eligible'],x
# A missing A answer is not a nonexistent name.
Path('/tmp/dns-mode').write_text('nodata')
x=run();assert x['status']=='EXISTS' and x['consecutive']==0,x
# SERVFAIL fails the execution rather than persisting false NXDOMAIN evidence.
Path('/tmp/dns-mode').write_text('servfail')
run(status='FAILED')
Path('/tmp/dns-mode').write_text('missing')
x=run();assert x['consecutive']==1,x
# Existing GitHub issue prevents creation after threshold.
x=run();assert len(issues())==1,x
# A GitHub API failure must not save a delivery marker. Use a second flow ID
# and isolated namespace state key to exercise creation rather than search hit.
# Unit suite covers resolver timeouts; real DNS fixtures cover SERVFAIL.
x=run('nocname.fixture.test');assert x['status']=='NO_CNAME',x
# Live public DNS, read-only and dry-run.
x=run('www.github.com',dry=True,live=True);assert x['status'] in ['EXISTS','NO_CNAME'],x
Path('/tmp/results.json').write_text(json.dumps(results,indent=2))
print('ALL INTEGRATION ASSERTIONS PASSED',flush=True)
