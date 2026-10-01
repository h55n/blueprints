import json,tempfile,subprocess,unittest,sys
from pathlib import Path
SCRIPT=Path(__file__).with_name('summarize.py')
class Reports(unittest.TestCase):
 def run_report(self,payload):
  with tempfile.TemporaryDirectory() as work:
   Path(work,'lychee.json').write_text(json.dumps(payload));r=subprocess.run([sys.executable,str(SCRIPT)],cwd=work,text=True,capture_output=True)
   if r.returncode:return r,None
   return r,json.loads(Path(work,'link-audit.json').read_text())
 def test_status_classification(self):
  entries=[{'url':f'https://test.invalid/{code}','status':{'code':code,'text':str(code)},'span':{'line':i+1}} for i,code in enumerate([404,410,403,429,500,503])]
  _,d=self.run_report({'total':6,'error_map':{'README.md':entries}})
  self.assertEqual(len(d['needs_fix']),2);self.assertEqual(len(d['needs_recheck']),4)
 def test_local_absence(self):
  _,d=self.run_report({'error_map':{'x.md':[{'url':'file:///missing.md','status':{'text':'File not found. Check if file exists and path is correct'}}]}})
  self.assertEqual(len(d['needs_fix']),1)
 def test_timeout_uncertain(self):
  _,d=self.run_report({'timeout_map':{'x.md':[{'url':'https://test.invalid/timeout'}]}})
  self.assertEqual(len(d['needs_fix']),0);self.assertEqual(len(d['needs_recheck']),1)
 def test_success_exclusions_not_relabelled(self):
  _,d=self.run_report({'total':4,'successful':2,'excludes':2})
  self.assertEqual(d['successful'],2);self.assertEqual(d['excluded'],2);self.assertEqual(d['needs_fix'],[])
 def test_invalid_json_fails(self):
  with tempfile.TemporaryDirectory() as work:
   Path(work,'lychee.json').write_text('');r=subprocess.run([sys.executable,str(SCRIPT)],cwd=work,capture_output=True)
   self.assertNotEqual(r.returncode,0)
 def test_missing_input_fails(self):
  with tempfile.TemporaryDirectory() as work:
   r=subprocess.run([sys.executable,str(SCRIPT)],cwd=work,capture_output=True);self.assertNotEqual(r.returncode,0)
unittest.main(verbosity=2)
