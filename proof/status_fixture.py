import json,subprocess,threading,time,tempfile,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=='/slow':time.sleep(3)
        if self.path=='/redirect':
            self.send_response(302);self.send_header('Location','/ok');self.end_headers();return
        self.send_response({'/ok':200,'/missing':404,'/gone':410,'/auth':403,'/rate':429,'/error':503,'/slow':200}.get(self.path,404));self.end_headers()
        try:self.wfile.write(b'fixture')
        except BrokenPipeError:pass
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
with tempfile.TemporaryDirectory() as work:
    p=Path(work)
    names=['ok','redirect','missing','gone','auth','rate','error','slow']
    (p/'fixture.md').write_text('\n'.join(f'[{name}](http://127.0.0.1:{server.server_port}/{name})' for name in names))
    r=subprocess.run(['lychee','--config','/dev/null','--no-progress','--max-concurrency','1','--max-retries','0','--timeout','1','--format','json',str(p/'fixture.md')],capture_output=True,text=True)
    assert r.returncode==2,r.stderr
    raw=json.loads(r.stdout);assert raw['successful']==2 and raw['timeouts']==1,raw
    (p/'lychee.json').write_text(r.stdout)
    rr=subprocess.run([sys.executable,'/proof/summarize.py'],cwd=work,capture_output=True,text=True);assert rr.returncode==0,rr.stderr
    report=json.loads((p/'link-audit.json').read_text());assert len(report['needs_fix'])==2 and len(report['needs_recheck'])==4,report
    Path('/evidence/status-fixture.json').write_text(json.dumps({'raw':raw,'report':report},indent=2));print('Real container HTTP fixture PASS: 200/redirect good; 404/410 inspect; 403/429/503/timeout recheck')
server.shutdown()
