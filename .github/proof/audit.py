"""Bounded wheel archive RECORD audit. Does not import, install or extract code."""
import base64,csv,hashlib,io,json,os,posixpath,re,stat,zipfile
from pathlib import Path
MAX_ARCHIVE=25*1024*1024
MAX_EXPANDED=100*1024*1024
MAX_FILES=10000
MAX_RECORD=4*1024*1024
class InvalidWheel(ValueError):pass
def require(ok,msg):
 if not ok:raise InvalidWheel(msg)
def safe_name(name):
 require(name and '\\' not in name and not name.startswith('/') and '\x00' not in name,'unsafe archive path')
 require(not re.match(r'^[A-Za-z]:',name),'drive-qualified path')
 require(all(p not in ['.','..',''] for p in name.rstrip('/').split('/')),'non-canonical archive path')
 return name

def audit(path):
 p=Path(path);require(0<p.stat().st_size<=MAX_ARCHIVE,'archive size out of bounds')
 findings=[]
 with zipfile.ZipFile(p) as z:
  infos=z.infolist();require(0<len(infos)<=MAX_FILES,'entry count out of bounds');names=[safe_name(i.filename) for i in infos];require(len(set(names))==len(names),'duplicate archive path')
  require(sum(i.file_size for i in infos)<=MAX_EXPANDED,'expanded size exceeds bound')
  for i in infos:
   require(not i.flag_bits&1,'encrypted member');require(not stat.S_ISLNK(i.external_attr>>16),'symlink member')
   require(i.compress_type in [zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED],'unsupported compression')
  files={i.filename:i for i in infos if not i.is_dir()};roots={n.split('/')[0] for n in files if n.split('/')[0].endswith('.dist-info')};require(len(roots)==1,'expected one top-level dist-info directory');root=next(iter(roots));record=root+'/RECORD'
  for n in ['METADATA','WHEEL','RECORD']:require(root+'/'+n in files,'missing required '+n)
  require(files[record].file_size<=MAX_RECORD,'RECORD exceeds bound')
  text=z.read(record).decode('utf-8');rows=list(csv.reader(io.StringIO(text,newline='')));require(len(rows)<=MAX_FILES,'RECORD row count exceeds bound');entries={}
  for row in rows:
   require(len(row)==3,'RECORD row must have three columns');name=safe_name(row[0]);require(name not in entries,'duplicate RECORD path');entries[name]=row[1:]
  signatures={root+'/RECORD.jws',root+'/RECORD.p7s'}
  for name in entries:
   if name not in files:findings.append({'path':name,'reason':'recorded file missing from archive'})
   if name in signatures:findings.append({'path':name,'reason':'signature must not appear in RECORD'})
  checked=0
  for name,info in files.items():
   if name in signatures:continue
   if name not in entries:findings.append({'path':name,'reason':'archive file missing from RECORD'});continue
   digest,size=entries[name]
   if name==record:
    if digest or size:findings.append({'path':name,'reason':'RECORD self hash/size must be empty'})
    continue
   if not re.fullmatch(r'0|[1-9][0-9]*',size) or int(size)!=info.file_size:findings.append({'path':name,'reason':'size mismatch or invalid size'})
   try:
    algorithm,encoded=digest.split('=',1);require(algorithm in ['sha256','sha384','sha512'],'unsupported or weak hash algorithm');require(bool(re.fullmatch(r'[A-Za-z0-9_-]+',encoded)),'invalid unpadded base64url digest');expected=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4));h=hashlib.new(algorithm);require(len(expected)==h.digest_size,'incorrect digest length');require(base64.urlsafe_b64encode(expected).rstrip(b'=').decode()==encoded,'non-canonical digest')
    with z.open(info) as f:
     observed=0
     while True:
      chunk=f.read(65536)
      if not chunk:break
      observed+=len(chunk);require(observed<=info.file_size,'member larger than declaration');h.update(chunk)
    if h.digest()!=expected:findings.append({'path':name,'reason':'hash mismatch'})
    checked+=1
   except (ValueError,InvalidWheel) as e:findings.append({'path':name,'reason':str(e)})
  # Even excluded signature files must have readable ZIP CRCs; they are not verified signatures.
  for name in signatures & files.keys():
   with z.open(name) as f:
    while f.read(65536):pass
  return {'valid':not findings,'files_checked':checked,'archive_files':len(files),'expanded_bytes':sum(i.file_size for i in infos),'findings':findings,'signature_files':sorted(signatures & files.keys()),'scope':'internal RECORD integrity only; not publisher authenticity, malware or vulnerability clearance'}
def main():
 try:report=audit('candidate.whl')
 except (InvalidWheel,ValueError,UnicodeError,csv.Error,zipfile.BadZipFile,NotImplementedError,RuntimeError,OSError) as e:report={'valid':False,'findings':[{'reason':str(e)}],'scope':'internal RECORD integrity only; not publisher authenticity, malware or vulnerability clearance'}
 Path('wheel-audit.json').write_text(json.dumps(report,indent=2));print('::'+json.dumps({'outputs':{'valid':report['valid']}})+'::')
if __name__=='__main__':main()
