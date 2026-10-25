import json,threading,os
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from dnslib import RR,QTYPE,RCODE,A,CNAME
from dnslib.server import DNSServer,BaseResolver

class DNS(BaseResolver):
    def resolve(self,request,handler):
        q=str(request.q.qname).rstrip('.')
        reply=request.reply()
        mode=Path('/tmp/dns-mode').read_text().strip()
        if q=='timeout.fixture.test':
            reply.header.rcode=RCODE.SERVFAIL
        elif q.endswith('.fixture.test') and request.q.qtype==QTYPE.CNAME:
            if q.startswith('nocname.'):
                pass
            else:
                target='gone.fixture.test' if mode!='changed' else 'other.fixture.test'
                reply.add_answer(RR(q,QTYPE.CNAME,rdata=CNAME(target),ttl=0))
        elif q in ['gone.fixture.test','other.fixture.test']:
            if mode=='exists':
                reply.add_answer(RR(q,QTYPE.A,rdata=A('192.0.2.1'),ttl=0))
            elif mode=='nodata':
                pass
            elif mode=='servfail':
                reply.header.rcode=RCODE.SERVFAIL
            else:
                reply.header.rcode=RCODE.NXDOMAIN
        else:
            reply.header.rcode=RCODE.NXDOMAIN
        return reply

issues=[]
class GitHub(BaseHTTPRequestHandler):
    def do_GET(self):
        # No real GitHub calls or account tokens used in this harness.
        payload={'total_count':len(issues),'incomplete_results':False,'items':issues}
        self.send_response(200);self.send_header('content-type','application/json');self.end_headers();self.wfile.write(json.dumps(payload).encode())
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['content-length'])))
        if Path('/tmp/gh-fail').exists():
            self.send_response(500);self.end_headers();return
        issue=dict(data,id=len(issues)+1,number=len(issues)+1,state='open',html_url='http://localhost:9998/fixture/1',url='http://localhost:9998/repos/test/dns/issues/1',user={'login':'fixture','id':1},created_at='2026-10-25T00:00:00Z',updated_at='2026-10-25T00:00:00Z')
        issues.append(issue)
        Path('/tmp/gh-issues.json').write_text(json.dumps(issues))
        self.send_response(201);self.send_header('content-type','application/json');self.end_headers();self.wfile.write(json.dumps(issue).encode())
    def log_message(self,*args):pass

Path('/tmp/dns-mode').write_text('missing')
Path('/tmp/gh-issues.json').write_text('[]')
DNSServer(DNS(),address=os.environ['DOCKER_BRIDGE'],port=53).start_thread()
HTTPServer(('0.0.0.0',9998),GitHub).serve_forever()
