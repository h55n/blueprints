import unittest,tempfile,zipfile,hashlib,base64,csv,io,sys
from pathlib import Path
from audit import audit,InvalidWheel
from unittest.mock import patch
ROOT='demo-1.0.dist-info/'
def fixture(path,kind='clean'):
 files={'demo/__init__.py':b'print("never execute me")\n',ROOT+'METADATA':b'Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n',ROOT+'WHEEL':b'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
 if kind=='traversal':files['../escape']=b'x'
 if kind=='absolute':files['/escape']=b'x'
 if kind=='backslash':files['a\\b']=b'x'
 if kind=='drive':files['C:escape']=b'x'
 rows=[]
 for name,data in files.items():
  h=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode();rows.append([name,'sha256='+h,str(len(data))])
 rows.append([ROOT+'RECORD','',''])
 if kind=='bad-hash':rows[0][1]='sha256='+'A'*43
 if kind=='weak':rows[0][1]='sha1=abc'
 if kind=='missing-row':rows.pop(0)
 if kind=='missing-file':files.pop('demo/__init__.py')
 if kind=='wrong-size':rows[0][2]='123'
 if kind=='duplicate-record':rows.append(rows[0])
 if kind=='self-hash':rows[-1][1]='sha256=abc'
 if kind=='short-row':rows[0]=['x','y']
 if kind=='bad-base64':rows[0][1]='sha256=??'
 if kind=='padded':rows[0][1]+='='
 if kind=='signatures':files[ROOT+'RECORD.jws']=b'not-verified-signature'
 if kind=='recorded-signature':files[ROOT+'RECORD.jws']=b'x';rows.append([ROOT+'RECORD.jws','',''])
 s=io.StringIO(newline='');csv.writer(s).writerows(rows);files[ROOT+'RECORD']=s.getvalue().encode()
 if kind=='no-metadata':files.pop(ROOT+'METADATA')
 if kind=='multiple-dist-info':files['other-1.dist-info/METADATA']=b'x'
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in files.items():
   if kind=='symlink' and name=='demo/__init__.py':
    i=zipfile.ZipInfo(name);i.external_attr=0o120777<<16;z.writestr(i,data)
   else:z.writestr(name,data)
  if kind=='duplicate-zip':z.writestr('demo/__init__.py',b'x')
class Tests(unittest.TestCase):
 def test_live_wheel(self):
  r=audit(Path(__file__).parent/'packaging-25.0-py3-none-any.whl');self.assertTrue(r['valid']);self.assertGreater(r['files_checked'],10)
 def test_resource_bounds(self):
  for field,value in [('MAX_ARCHIVE',10),('MAX_EXPANDED',10),('MAX_FILES',1),('MAX_RECORD',1)]:
   with self.subTest(bound=field),tempfile.TemporaryDirectory() as d:
    p=Path(d)/'test.whl';fixture(p)
    with patch('audit.'+field,value),self.assertRaises(InvalidWheel):audit(p)
 def test_empty_and_nonzip(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.whl';p.write_bytes(b'')
   with self.assertRaises(InvalidWheel):audit(p)
   p.write_bytes(b'not a ZIP archive')
   with self.assertRaises(zipfile.BadZipFile):audit(p)
 def test_matrix(self):
  cases=['clean','signatures','traversal','absolute','backslash','drive','bad-hash','weak','missing-row','missing-file','wrong-size','duplicate-record','self-hash','short-row','bad-base64','padded','recorded-signature','no-metadata','multiple-dist-info','symlink','duplicate-zip']
  for kind in cases:
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
    p=Path(d)/'test.whl';fixture(p,kind)
    try:r=audit(p);valid=r['valid']
    except InvalidWheel:valid=False
    self.assertEqual(valid,kind in ['clean','signatures'])
if __name__=='__main__':unittest.main(verbosity=2)
