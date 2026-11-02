import subprocess,time,requests,pathlib,yaml,json,copy,sys,os
sys.path.insert(0,str(pathlib.Path(__file__).parent));from test_audit import fixture
r=pathlib.Path(os.environ['PROOF_RUNTIME']);out=pathlib.Path(os.environ['PROOF_OUTPUT']);out.mkdir(parents=True,exist_ok=True);java=pathlib.Path(os.environ['JAVA_HOME'])/'bin/java';log=open(out/'server.log','w');p=subprocess.Popen([str(java),'-Xmx650m','-jar',str(r/'kestra'),'server','local','-c',str(r/'config.yml'),'-p',str(r/'plugins'),'--port=8090','--worker-thread=2','--no-tutorials'],stdout=log,stderr=subprocess.STDOUT)
s=requests.Session();base='http://127.0.0.1:8090/api/v1';rows=[]
def call(path,**kw):
 x=s.request(kw.pop('method','GET'),base+path,timeout=25,**kw)
 if not x.ok:print('HTTPERROR',x.status_code,x.text[:3000],flush=True)
 x.raise_for_status();return x.json()
try:
 for _ in range(60):
  try:call('/flows/search');break
  except requests.RequestException:time.sleep(1)
 else:raise RuntimeError('server not ready')
 original=yaml.safe_load((pathlib.Path('flows/python-wheel-record-integrity-gate.yaml')).read_text());original.pop('extend')
 for name in ['live-clean','bad-hash','traversal','duplicate-zip','wrong-size','oversized']:
  flow=copy.deepcopy(original);flow['id']='wheel-record-nov2-'+name
  call('/flows',method='POST',data=yaml.safe_dump(flow),headers={'Content-Type':'application/x-yaml'})
  path=out/(name+'.whl')
  if name=='live-clean':path=out/'packaging-25.0-py3-none-any.whl'
  elif name=='oversized':
   with open(path,'wb')as f:f.truncate(26214401)
  else:fixture(path,name)
  with open(path,'rb')as f:ex=call('/executions/company.packaging/'+flow['id'],method='POST',files={'wheel':(path.name,f,'application/octet-stream')})
  eid=ex['id'];deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   ex=call('/executions/'+eid)
   if ex['state']['current']in ['SUCCESS','FAILED','WARNING','KILLED']:break
   time.sleep(.5)
  (out/(name+'-execution.json')).write_text(json.dumps(ex,indent=2));(out/(name+'-logs.json')).write_text(json.dumps(call('/logs/'+eid+'?minLevel=TRACE'),indent=2));expected='SUCCESS'if name=='live-clean'else'FAILED';row=dict(label=name,execution_id=eid,state=ex['state']['current'],expected=expected,tasks=[(t['taskId'],t['state']['current'])for t in ex.get('taskRunList',[])],passed=ex['state']['current']==expected);rows.append(row);(out/'runtime-results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True);assert row['passed'],row
finally:
 p.terminate()
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:p.kill();p.wait()
