import requests,time,json,pathlib,yaml,hashlib,zipfile,io
cfg=yaml.safe_load(pathlib.Path('/tmp/kestra-runtime/config.yml').read_text());a=cfg['kestra']['server']['basic-auth'];s=requests.Session();s.auth=(a['username'],a['password']);base='http://127.0.0.1:18080/api/v1/main'
for i in range(30):
 try:
  if s.get(base+'/flows/search',timeout=2).status_code==200:break
 except requests.RequestException:pass
 time.sleep(1)
flow=pathlib.Path('flows/sentinel2-cloud-masked-ndvi-geotiff.yaml').read_text().split('\nextend:')[0]
existing=s.get(base+'/flows/company.team/sentinel2-cloud-masked-ndvi-geotiff')
if existing.status_code==404:
 r=s.post(base+'/flows',headers={'Content-Type':'application/x-yaml'},data=flow)
else:
 existing.raise_for_status()
 r=s.put(base+'/flows/company.team/sentinel2-cloud-masked-ndvi-geotiff',headers={'Content-Type':'application/x-yaml'},data=flow)
r.raise_for_status()
cases=[('normal',{},'SUCCESS'),('none',{'start_date':'2010-01-01','end_date':'2010-01-02'},'SUCCESS'),('cloudy',{'bbox':'[77.58,12.96,77.60,12.98]','max_cloud_pct':'80','min_valid_fraction':'.2'},'FAILED'),('bad_bbox',{'bbox':'[1,2,0,3]'},'FAILED'),('too_large',{'bbox':'[0,0,1,1]'},'FAILED'),('bad_dates',{'start_date':'2026-09-30','end_date':'2026-09-01'},'FAILED'),('bad_cloud',{'max_cloud_pct':'101'},'FAILED'),('bad_fraction',{'min_valid_fraction':'0'},'FAILED')]
results=[]
for name,over,expected in cases:
 inputs={'start_date':'2026-09-01','end_date':'2026-09-30',**over};r=s.post(base+'/executions/company.team/sentinel2-cloud-masked-ndvi-geotiff',files={k:(None,v) for k,v in inputs.items()});r.raise_for_status();eid=r.json()['id']
 for i in range(65):
  j=s.get(base+'/executions/'+eid).json();state=j['state']['current']
  if state in ['SUCCESS','FAILED','WARNING','KILLED']:break
  time.sleep(.6)
 pathlib.Path('/tmp/stac-blueprint/'+name+'-execution.json').write_text(json.dumps(j,indent=2))
 logs=s.get(base+'/logs/'+eid).json();pathlib.Path('/tmp/stac-blueprint/'+name+'-logs.json').write_text(json.dumps(logs,indent=2))
 tasks={t['taskId']:t['state']['current'] for t in j.get('taskRunList',[])};print(name,state,tasks,flush=True)
 assert state==expected,(name,state)
 if name=='none':assert 'package_verified_raster' not in tasks and tasks.get('no_matching_scene')=='SUCCESS'
 if name=='normal':
  tid=next(t for t in j['taskRunList'] if t['taskId']=='package_verified_raster')['id']
  uri=s.get(base+'/outputs/tasks/'+eid+'/'+tid).json()['uri']
  r=s.get(base+'/executions/'+eid+'/file',params={'path':uri});r.raise_for_status();pathlib.Path('/tmp/stac-blueprint/verified.zip').write_bytes(r.content)
  z=zipfile.ZipFile(io.BytesIO(r.content));m=json.loads(z.read('manifest.json'));print('ARTIFACT',m['valid_fraction'],m['shape'],z.namelist(),flush=True)
  for line in z.read('SHA256SUMS').decode().splitlines():
   digest,f=line.split('  ');assert hashlib.sha256(z.read(f)).hexdigest()==digest
 results.append({'case':name,'execution':eid,'state':state,'tasks':tasks})
pathlib.Path('/tmp/stac-blueprint/matrix-results.json').write_text(json.dumps(results,indent=2))
