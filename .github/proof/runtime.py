import subprocess,time,requests,pathlib,yaml,json,copy,itertools,hashlib,os
r=pathlib.Path(os.environ['PROOF_RUNTIME']);out=pathlib.Path(os.environ['PROOF_OUTPUT']);out.mkdir(parents=True,exist_ok=True);java=pathlib.Path(os.environ['JAVA_HOME'])/'bin/java';log=open(out/'server.log','w');p=subprocess.Popen([str(java),'-Xmx650m','-jar',str(r/'kestra'),'server','local','-c',str(r/'config.yml'),'-p',str(r/'plugins'),'--port=8090','--worker-thread=2','--no-tutorials'],stdout=log,stderr=subprocess.STDOUT)
s=requests.Session();base='http://127.0.0.1:8090/api/v1';results=[]
def call(path,**kw):
 x=s.request(kw.pop('method','GET'),base+path,timeout=25,**kw);x.raise_for_status();return x.json()
def run(flow,inputs,expected,label):
 call('/flows',method='POST',data=yaml.safe_dump(flow),headers={'Content-Type':'application/x-yaml'})
 ex=call('/executions/company.infrastructure/'+flow['id'],method='POST',files={k:(None,v) for k,v in inputs.items()} or {'_':(None,'')});eid=ex['id'];deadline=time.monotonic()+150
 while time.monotonic()<deadline:
  ex=call('/executions/'+eid)
  if ex['state']['current']in ['SUCCESS','FAILED','WARNING','KILLED']:break
  time.sleep(.5)
 (out/(label+'-execution.json')).write_text(json.dumps(ex,indent=2));logs=call('/logs/'+eid+'?minLevel=TRACE');(out/(label+'-logs.json')).write_text(json.dumps(logs,indent=2));row=dict(label=label,inputs=inputs,execution_id=eid,state=ex['state']['current'],expected=expected,tasks=[(t['taskId'],t['state']['current'])for t in ex.get('taskRunList',[])],passed=ex['state']['current']==expected);results.append(row);(out/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(row),flush=True)
 assert row['passed'],row
try:
 for _ in range(60):
  try:call('/flows/search');break
  except requests.RequestException:time.sleep(1)
 else:raise RuntimeError('server not ready')
 path=pathlib.Path('flows/ubuntu-signed-repository-index-gate.yaml');original=yaml.safe_load(path.read_text());original.pop('extend');(out/'yaml.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
 for suite,component,arch in itertools.product(['noble-updates','jammy-updates'],['main','universe'],['amd64','i386']):
  label='-'.join([suite,component,arch]);flow=copy.deepcopy(original);flow['id']='ubuntu-nov2-'+label;run(flow,dict(suite=suite,component=component,architecture=arch),'SUCCESS',label)
 for name in ['untrusted-key','wrong-hash']:
  flow=copy.deepcopy(original);flow['id']='ubuntu-nov2-'+name
  if name=='untrusted-key':flow['tasks'][0]['script']=flow['tasks'][0]['script'].replace('/usr/share/keyrings/ubuntu-archive-keyring.gpg','/nonexistent-keyring.gpg')
  if name=='wrong-hash':flow['tasks'][1]['script']=flow['tasks'][1]['script'].replace("observed == report['sha256']","observed == '0' * 64")
  run(flow,{},'FAILED',name)
finally:
 p.terminate()
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:p.kill();p.wait()
