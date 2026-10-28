import requests,yaml,pathlib,subprocess,os,time,json,signal
root=pathlib.Path('/tmp/oisst-blueprint');root.mkdir(exist_ok=True);cfg=yaml.safe_load(pathlib.Path('/tmp/kestra-runtime/config.yml').read_text());a=cfg['kestra']['server']['basic-auth'];s=requests.Session();s.auth=(a['username'],a['password']);base='http://127.0.0.1:18080/api/v1/main'
env=dict(os.environ);env['JAVA_HOME']=os.environ.get('JAVA_HOME','/tmp/kestra-runtime/jdk-25.0.5+8-jre');env['PATH']=env['JAVA_HOME']+'/bin:'+env['PATH']
f=open(root/'runtime.log','w');p=subprocess.Popen([env['JAVA_HOME']+'/bin/java','-jar','/tmp/kestra-runtime/kestra','server','local','--config','/tmp/kestra-runtime/config.yml','--plugins','/tmp/kestra-runtime/plugins','--no-tutorials','--worker-thread','4'],cwd='/tmp/kestra-runtime',env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
try:
 for _ in range(40):
  try:
   if s.get(base+'/flows/search',timeout=1).status_code==200:break
  except requests.RequestException:pass
  time.sleep(1)
 else:raise RuntimeError('server not ready')
 flow=pathlib.Path('flows/noaa-oisst-netcdf-to-regional-zarr.yaml').read_text().split('\nextend:')[0]
 url=base+'/flows/company.data/noaa-oisst-netcdf-to-regional-zarr';ex=s.get(url)
 r=s.post(base+'/flows',data=flow,headers={'Content-Type':'application/x-yaml'}) if ex.status_code==404 else s.put(url,data=flow,headers={'Content-Type':'application/x-yaml'})
 print('CREATE',r.status_code,r.text[:400],flush=True);r.raise_for_status()
 r=s.post(base+'/executions/company.data/noaa-oisst-netcdf-to-regional-zarr',files={'day':(None,'2024-07-01'),'bbox':(None,'[65,5,80,20]')});r.raise_for_status();eid=r.json()['id'];print('ID',eid,flush=True)
 for _ in range(95):
  j=s.get(base+'/executions/'+eid).json();state=j['state']['current']
  if state in ['SUCCESS','FAILED','WARNING','KILLED']:break
  time.sleep(.5)
 (root/'runtime-execution.json').write_text(json.dumps(j,indent=2));logs=s.get(base+'/logs/'+eid).json();(root/'runtime-logs.json').write_text(json.dumps(logs,indent=2))
 assert state=='SUCCESS',state
 print('STATE',state,[(t['taskId'],t['state']['current']) for t in j.get('taskRunList',[])],flush=True)
 if state=='SUCCESS':
  import zipfile,io,hashlib
  tid=next(t for t in j['taskRunList'] if t['taskId']=='package_verified_store')['id']
  uri=s.get(base+'/outputs/tasks/'+eid+'/'+tid).json()['uri']
  r=s.get(base+'/executions/'+eid+'/file',params={'path':uri});r.raise_for_status();(root/'runtime-verified.zip').write_bytes(r.content)
  z=zipfile.ZipFile(io.BytesIO(r.content))
  for line in z.read('SHA256SUMS').decode().splitlines():
   digest,name=line.split('  ');assert hashlib.sha256(z.read(name)).hexdigest()==digest
  print('DOWNLOADED verified',z.namelist(),flush=True)
  z.extractall(root/'downloaded')
 cases=[('bad_bbox',{'bbox':'[0,0,31,1]'}),('recent_date',{'day':'2099-01-01'}),('land_only',{'bbox':'[77.5,12.5,78,13]'}),('no_centers',{'bbox':'[0.01,0.01,0.02,0.02]'})]

 for name,over in cases:
  r=s.post(base+'/executions/company.data/noaa-oisst-netcdf-to-regional-zarr',files={k:(None,v) for k,v in {'day':'2024-07-01','bbox':'[65,5,80,20]',**over}.items()});r.raise_for_status();testid=r.json()['id']
  for _ in range(80):
   t=s.get(base+'/executions/'+testid).json();st=t['state']['current']
   if st in ['SUCCESS','FAILED','WARNING','KILLED']:break
   time.sleep(.3)
  (root/(name+'-execution.json')).write_text(json.dumps(t,indent=2))
  assert st=='FAILED',(name,st)
  assert not any(x['taskId']=='package_verified_store' for x in t.get('taskRunList',[]))
  print('NEGATIVE',name,st,[(x['taskId'],x['state']['current']) for x in t.get('taskRunList',[])],flush=True)
 for l in logs:
  if l.get('level') in ['ERROR','WARN']:print(l.get('message'),flush=True)
finally:
 os.killpg(p.pid,signal.SIGTERM)
 try:p.wait(timeout=8)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 f.close()
