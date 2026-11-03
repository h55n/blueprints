import http.server,ssl,threading,tempfile,subprocess,os,json,hashlib,sys
from pathlib import Path
root=Path(os.environ['PROOF_OUTPUT']);cert=root/'localhost.crt';key=root/'localhost.key';body=b'known wheel';digest=hashlib.sha256(body).hexdigest();filename='demo_gate-9.0-py3-none-any.whl'
mode='tampered';fetched=[]
class H(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  fetched.append(self.path)
  if '/+f/'in self.path:content=b'tampered' if mode=='tampered'else body
  else:
   if mode=='redirect':self.send_response(302);self.send_header('Location','https://elsewhere.invalid/x');self.end_headers();return
   url=('https://elsewhere.invalid' if mode=='cross-origin'else'https://localhost:3149')+'/root/prod/+f/123/456/'+filename
   links=[{'rel':'releasefile','href':url}]
   if mode=='duplicate':links*=2
   content=json.dumps({'result':{'+links':links}}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
 def log_message(self,*a):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',3149),H);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cert,key);server.socket=ctx.wrap_socket(server.socket,server_side=True);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 for mode in ['tampered','redirect','cross-origin','duplicate']:
  fetched=[]
  with tempfile.TemporaryDirectory()as work:
   p=Path(work);(p/'verification.json').write_text(json.dumps({'filename':filename,'name':'demo-gate','version':'9.0','sha256':digest}))
   x=subprocess.run([sys.executable,str(root/'readback.py')],cwd=work,env=os.environ|{'TARGET_INDEX':'https://localhost:3149/root/prod','SSL_CERT_FILE':str(cert)},capture_output=True,text=True)
   assert x.returncode!=0 and not(p/'promotion-receipt.json').exists(),mode
   assert len(fetched)==(2 if mode=='tampered'else 1),(mode,fetched)
   print(mode,'PASS',x.stderr.splitlines()[-1])
finally:server.shutdown();thread.join();server.server_close()
