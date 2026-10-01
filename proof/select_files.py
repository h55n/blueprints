import glob,json,os
from pathlib import Path
root=Path('repository').resolve()
pattern=os.environ['MARKDOWN_GLOB']
if pattern.startswith(('/', '-')) or '..' in Path(pattern).parts or '\n' in pattern:
    raise ValueError('Use a relative Markdown glob without parent traversal')
selected=[]
for name in sorted(glob.glob(str(root/pattern),recursive=True)):
    path=Path(name)
    if not path.is_file() or path.suffix.lower() not in ('.md','.markdown'):continue
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Markdown files must stay inside the checkout, without symlinks')
    if path.stat().st_size>1_000_000:raise ValueError('Markdown file exceeds 1 MB; narrow the scope')
    selected.append(str(path.relative_to(root)))
if not selected:raise ValueError('No Markdown files matched; an empty scan is not success')
if len(selected)>50:raise ValueError('More than 50 files matched; narrow the scope')
Path('repository/markdown-files.txt').write_text('\n'.join(selected)+'\n')
print('Selected',len(selected),'Markdown files')
