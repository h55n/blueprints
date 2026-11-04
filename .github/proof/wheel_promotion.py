import subprocess, time, requests, pathlib, yaml, json, copy, sys, os
import zipfile, hashlib, ssl, threading, http.server, tempfile
from pathlib import Path
root = Path(os.environ['PROOF_OUTPUT'])
root.mkdir(parents=True, exist_ok=True)
v = Path(sys.executable).parent
cert, key = root/'localhost.crt', root/'localhost.key'
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
subprocess.run([str(v/'devpi-init'),'--serverdir',str(root/'registry'),'--no-root-pypi'], check=True)
class Proxy(http.server.BaseHTTPRequestHandler):
 def do_GET(self):self.proxy()
 def do_POST(self):self.proxy()
 def proxy(self):
  data=self.rfile.read(int(self.headers.get('Content-Length',0))) if self.command=='POST' else None
  headers={k:z for k,z in self.headers.items()if k.lower()not in ['host','content-length','connection']}
  try:r=requests.request(self.command,'http://127.0.0.1:3147'+self.path,data=data,headers=headers,timeout=10)
  except Exception:self.send_error(502);return
  self.send_response(r.status_code)
  for k,z in r.headers.items():
   if k.lower()not in ['transfer-encoding','content-length','connection','content-encoding']:self.send_header(k,z)
  self.send_header('Content-Length',str(len(r.content)));self.end_headers();self.wfile.write(r.content)
 def log_message(self,*a):pass
httpd=http.server.ThreadingHTTPServer(('127.0.0.1',3148),Proxy);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);httpd.socket=ctx.wrap_socket(httpd.socket,server_side=True);thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
log=open(root/'test-server.log','w');server=subprocess.Popen([str(v/'devpi-server'),'--serverdir',str(root/'registry'),'--host','127.0.0.1','--port','3147','--outside-url','https://localhost:3148'],stdout=log,stderr=log)
r=Path(os.environ['PROOF_RUNTIME']);java=Path(os.environ['JAVA_HOME'])/'bin/java';kl=open(root/'kestra-server.log','w');kp=subprocess.Popen([str(java),'-Xmx600m','-jar',str(r/'kestra'),'server','local','-c',str(r/'config.yml'),'-p',str(r/'plugins'),'--port=8090','--worker-thread=2','--no-tutorials'],stdout=kl,stderr=subprocess.STDOUT,env=os.environ|{'PATH':str(v)+':'+os.environ['PATH'],'SSL_CERT_FILE':str(cert),'REQUESTS_CA_BUNDLE':str(cert)})
session=requests.Session();base='http://127.0.0.1:8090/api/v1';results=[]
def call(path,**kw):
 x=session.request(kw.pop('method','GET'),base+path,timeout=25,**kw)
 if not x.ok:print('HTTPERROR',x.status_code,x.text[:1500],flush=True)
 x.raise_for_status();return x.json()
try:
 for i in range(90):
  try:call('/flows/search');break
  except requests.RequestException:time.sleep(1)
 else:raise RuntimeError('Kestra did not start')
 requests.put('http://127.0.0.1:3147/root/prod',json={'type':'stage','bases':[],'volatile':False},auth=('root','')).raise_for_status()
 original=yaml.safe_load(Path('flows/devpi-trusted-wheel-promotion.yaml').read_text());meta=original.pop('extend')
 assert set(meta)=={'title','metaTitle','shortDescription','metaDescription','description','tags','subTags','ee','demo'}
 assert len(meta['metaDescription'])<=160 and meta['tags']==['Infrastructure'] and meta['subTags']==['CI/CD & Deployment'] and meta['ee'] is False and meta['demo'] is False
 validation=call('/flows/validate',method='POST',data=yaml.safe_dump(original),headers={'Content-Type':'application/x-yaml'})
 assert len(validation)==1 and not validation[0].get('constraints'),validation
 print('FULL_FLOW_MODEL_VALIDATION_PASS',validation,flush=True)
 for name in ('verify','upload_preflight','readback'):
  task=next(t for t in original['tasks'][0]['tasks'] if t['id']==name)
  (root/(name+'.py')).write_text(task['script'])
 for case in ['good','real-wheel','hash-mismatch','identity-mismatch','volatile-index','missing-lock','untrusted-adjacent-lock']:
  flow=copy.deepcopy(original);flow['id']='wheel-promotion-proof-'+case+'-'+str(int(time.time()))
  # Only inject disposable registry credentials and its test CA. Production YAML retains secrets.
  upload=next(t for t in flow['tasks'][0]['tasks'] if t['id']=='upload');upload['env']['TWINE_USERNAME']='root';upload['env']['TWINE_PASSWORD']='';upload['env']['SSL_CERT_FILE']=str(cert);upload['env']['REQUESTS_CA_BUNDLE']=str(cert)
  # The registry is disposable localhost HTTPS. Only test CA, networking and credentials differ.
  flow['tasks'][0]['inputFiles']['test-ca.pem']=Path(ssl.get_default_verify_paths().cafile).read_text() + '\n' + cert.read_text()
  for task in flow['tasks'][0]['tasks']:
   task['taskRunner']['networkMode']='host'
   task.setdefault('env',{})['SSL_CERT_FILE']='test-ca.pem'
   task['env']['REQUESTS_CA_BUNDLE']='test-ca.pem'
  call('/flows',method='POST',data=yaml.safe_dump(flow),headers={'Content-Type':'application/x-yaml'})
  version={'good':'3.0','hash-mismatch':'3.1','identity-mismatch':'3.2','volatile-index':'3.3','real-wheel':'25.0','missing-lock':'3.4','untrusted-adjacent-lock':'3.5'}[case];filename=f'demo_gate-{version}-py3-none-any.whl';wheel=root/(case+'.whl')
  with zipfile.ZipFile(wheel,'w')as z:
   z.writestr('demo_gate/__init__.py','VALUE = 1\n');z.writestr(f'demo_gate-{version}.dist-info/METADATA',f'Metadata-Version: 2.1\nName: demo-gate\nVersion: {version}\n');z.writestr(f'demo_gate-{version}.dist-info/WHEEL','Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n');z.writestr(f'demo_gate-{version}.dist-info/RECORD','')
  if case=='real-wheel':
   wheel=Path(os.environ['PROOF_WHEEL']);filename=wheel.name
   assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484'
  lock={'filename':filename,'name':'packaging'if case=='real-wheel'else'other'if case=='identity-mismatch'else'demo-gate','version':version,'sha256':('0'*64 if case=='hash-mismatch'else hashlib.sha256(wheel.read_bytes()).hexdigest())};lockpath=root/(case+'-lock.json');lockpath.write_text(json.dumps(lock));target='https://localhost:3148/root/prod'
  if case=='volatile-index':requests.put('http://127.0.0.1:3147/root/volatile4',json={'type':'stage','bases':[],'volatile':True},auth=('root','')).raise_for_status();target='https://localhost:3148/root/volatile4'
  kvurl=base+'/namespaces/company.release/kv/devpi.approved_release_lock'
  if case=='missing-lock':
   response=session.delete(kvurl,timeout=20)
   assert response.status_code in (200,204,404),response.text
  else:
   response=session.put(kvurl,data=json.dumps(lock),headers={'Content-Type':'text/plain'},timeout=20);response.raise_for_status()
  with wheel.open('rb')as w:
   files={'wheel':(filename,w),'target_index':(None,target)}
   if case=='untrusted-adjacent-lock':
    # An extra adjacent upload cannot override the trusted KV lock.
    trusted={**lock,'sha256':'0'*64}
    response=session.put(kvurl,data=json.dumps(trusted),headers={'Content-Type':'text/plain'},timeout=20);response.raise_for_status()
    files['release_lock']=('forged-lock.json',json.dumps(lock))
   ex=call('/executions/company.release/'+flow['id'],method='POST',files=files)
  eid=ex['id'];deadline=time.monotonic()+100
  while time.monotonic()<deadline:
   ex=call('/executions/'+eid)
   if ex['state']['current']in ['SUCCESS','FAILED','WARNING','KILLED']:break
   time.sleep(.5)
  logs=call('/logs/'+eid+'?minLevel=TRACE');(root/(case+'-execution.json')).write_text(json.dumps(ex,indent=2));(root/(case+'-logs.json')).write_text(json.dumps(logs,indent=2));expected='SUCCESS'if case in ('good','real-wheel')else'FAILED';row={'case':case,'id':eid,'state':ex['state']['current'],'expected':expected,'tasks':[(t['taskId'],t['state']['current'])for t in ex.get('taskRunList',[])]};results.append(row);print(row,flush=True)
  if row['state']!=expected:
   print(json.dumps(logs)[-6000:]);raise RuntimeError('unexpected outcome')
  if case not in ('good','real-wheel'):assert requests.get('http://127.0.0.1:3147/root/'+('volatile4'if case=='volatile-index'else'prod')+'/demo-gate/'+version,headers={'Accept':'application/json'}).status_code==404
 (root/'runtime-results.json').write_text(json.dumps(results,indent=2))
 subprocess.run([sys.executable, str(Path(__file__).with_name('wheel_promotion_adversarial.py'))],check=True)
finally:
 kp.terminate()
 try:kp.wait(timeout=15)
 except subprocess.TimeoutExpired:kp.kill();kp.wait()
 server.terminate();server.wait(timeout=10);httpd.shutdown();thread.join();httpd.server_close();log.close();kl.close();key.unlink(missing_ok=True)
