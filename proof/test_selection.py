import os,tempfile,subprocess,unittest,sys
from pathlib import Path
SCRIPT=Path(__file__).with_name('select_files.py')
class Selection(unittest.TestCase):
 def run_case(self,pattern,setup=None):
  with tempfile.TemporaryDirectory() as work:
   root=Path(work,'repository');root.mkdir();(root/'README.md').write_text('x')
   if setup:setup(root)
   r=subprocess.run([sys.executable,str(SCRIPT)],cwd=work,env={**os.environ,'MARKDOWN_GLOB':pattern},capture_output=True,text=True)
   return r.returncode,r.stdout,r.stderr
 def test_readme(self):self.assertEqual(self.run_case('README.md')[0],0)
 def test_empty(self):self.assertNotEqual(self.run_case('missing*.md')[0],0)
 def test_traversal(self):self.assertNotEqual(self.run_case('../*.md')[0],0)
 def test_absolute(self):self.assertNotEqual(self.run_case('/tmp/*.md')[0],0)
 def test_option(self):self.assertNotEqual(self.run_case('--help')[0],0)
 def test_symlink(self):self.assertNotEqual(self.run_case('link.md',lambda r:(r/'link.md').symlink_to('/etc/hosts'))[0],0)
 def test_large(self):self.assertNotEqual(self.run_case('README.md',lambda r:(r/'README.md').write_text('x'*1000001))[0],0)
 def test_scope(self):self.assertNotEqual(self.run_case('*.md',lambda r:[(r/f'{i}.md').write_text('x') for i in range(51)])[0],0)
unittest.main(verbosity=2)
