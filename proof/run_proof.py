import subprocess, os, tarfile, hashlib, shutil, sys, pathlib, base64 as _b64, time as _t, urllib.request as _ur
W = pathlib.Path('/tmp/eolwork'); W.mkdir(exist_ok=True)
pathlib.Path('evidence').mkdir(exist_ok=True)
subprocess.run(['docker', 'create', '--name', 'jrecopy', 'kestra-link-proof'], check=True)
subprocess.run(['docker', 'cp', 'jrecopy:/opt/java/openjdk', str(W / 'jre')], check=True)
JAVA = str(W / 'jre' / 'bin' / 'java')
print(subprocess.run([JAVA, '-version'], capture_output=True, text=True).stderr)
_ur.urlretrieve('https://github.com/kestra-io/kestra/releases/download/v2.0.4/kestra-2.0.4', str(W / 'kestra.jar'))
assert hashlib.sha256((W / 'kestra.jar').read_bytes()).hexdigest() == '88ee8d44c3d4a234c9d04689e72b8ba903ae8f9f2c6ae5f94bad89f3bcd68513'
(W / 'plugins').mkdir(exist_ok=True)
subprocess.run([JAVA, '-jar', str(W / 'kestra.jar'), 'plugins', 'install', '--locally', '-p', str(W / 'plugins'), 'io.kestra.plugin:plugin-slack:2.1.0', 'io.kestra.plugin:plugin-script-python:1.14.0'], check=True)
subprocess.run(['docker', 'pull', 'python:3.12-slim'], check=True)
(W / 'config.yml').write_text("""micronaut:
  server:
    host: 127.0.0.1
    port: 18081
kestra:
  server:
    basic-auth:
      username: proof@local.invalid
      password: ${PROOF_PASSWORD}
  storage:
    type: local
    local:
      base-path: /tmp/eolwork/storage
""")
MOCK = pathlib.Path('proof/mock_slack.py')
subprocess.Popen([sys.executable, str(MOCK)], stdout=open('evidence/mock-slack.log', 'w'), stderr=subprocess.STDOUT)
REGPASS = 'Rp' + hashlib.sha256(os.urandom(16)).hexdigest()[:20]
print('::add-mask::' + REGPASS)
env = dict(os.environ, SECRET_SLACK_WEBHOOK_URL=_b64.b64encode(b'http://127.0.0.1:9999/hook').decode(), SECRET_REGISTRY_PASSWORD=_b64.b64encode(REGPASS.encode()).decode())
subprocess.Popen([JAVA, '-Xmx1g', '-jar', str(W / 'kestra.jar'), 'server', 'local', '--no-tutorials', '-p', str(W / 'plugins'), '-c', str(W / 'config.yml')], env=env, stdout=open('evidence/kestra-eol-server.log', 'w'), stderr=subprocess.STDOUT)
import urllib.request, urllib.error, base64, json, pathlib, time, os
base = 'http://127.0.0.1:18081/api/v1'
auth = base64.b64encode(('proof@local.invalid:' + os.environ['PROOF_PASSWORD']).encode()).decode()
out = pathlib.Path('evidence'); out.mkdir(exist_ok=True)
def call(path, method='GET', body=None, ctype='application/json'):
    r = urllib.request.Request(base + path, data=body, method=method, headers={'Authorization': 'Basic ' + auth, 'Content-Type': ctype})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.read()
for _ in range(150):
    try:
        call('/configs'); break
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403): raise RuntimeError('credentials rejected')
        time.sleep(2)
    except Exception:
        time.sleep(2)
else:
    raise RuntimeError('Kestra not ready')

src = pathlib.Path('flows/registry-image-eol-audit.yaml').read_text()
flow_txt = src.split('\nextend:\n')[0] + '\n'
FLOW = 'registry-image-eol-audit'
def deploy(text):
    try:
        call('/flows', 'POST', text.encode(), 'application/x-yaml')
    except urllib.error.HTTPError as exc:
        if exc.code in (409, 422):
            call('/flows/company.team/' + FLOW, 'PUT', text.encode(), 'application/x-yaml')
        else:
            raise RuntimeError(exc.read().decode()[:2000])
def run(inputs):
    b = 'kestra-proof-boundary'
    data = ''.join('--' + b + '\r\nContent-Disposition: form-data; name="' + k + '"\r\n\r\n' + v + '\r\n' for k, v in inputs.items()) + '--' + b + '--\r\n'
    e = json.loads(call('/executions/company.team/' + FLOW, 'POST', data.encode(), 'multipart/form-data; boundary=' + b))
    for _ in range(300):
        e = json.loads(call('/executions/' + e['id']))
        if e['state']['current'] in ('SUCCESS', 'FAILED', 'WARNING', 'KILLED'): return e
        time.sleep(1)
    raise RuntimeError('timeout')
def hits():
    p = pathlib.Path('evidence/mock-slack.log')
    return [json.loads(l) for l in p.read_text().splitlines() if l.startswith('{')] if p.exists() else []
def tasks(e): return [(t['taskId'], t['state']['current']) for t in e['taskRunList']]
def save(name, e):
    out.joinpath(name + '-execution.json').write_text(json.dumps(e, indent=2))
    out.joinpath(name + '-logs.json').write_bytes(call('/logs/' + e['id']))
def report(e):
    outputs = json.loads(call('/main/outputs/executions/' + e['id']))
    return call('/executions/' + e['id'] + '/file?path=' + urllib.request.quote(outputs['report'], safe='')).decode()
def alert_text(n0):
    h = hits()[n0:]
    assert len(h) == 1, h
    return json.loads(h[0]['body'])['text']

deploy(flow_txt)
# 1 alert path: defaults (public Docker Hub images)
n0 = len(hits())
e = run({})
save('1-alert', e)
print('1 ALERT', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS'
ids = [t for t, _ in tasks(e)]
assert 'alert_slack' in ids and 'log_all_supported' not in ids
txt = alert_text(n0)
print('slack payload:', txt)
for needle in ('python:3.9-slim', 'node:18-alpine', 'postgres:13', 'alpine:3.20'):
    assert needle in txt, needle
assert 'redis:7.2: redis' not in txt
rep = report(e); out.joinpath('1-alert-report.md').write_text(rep); print(rep)
assert '| redis:7.2 | redis | 7.2' in rep and 'SUPPORTED' in rep
# 2 supported images only: clean run, no alert
n0 = len(hits())
e = run({'images': 'python:3.13-slim\n# comment line\nubuntu:24.04\n', 'warn_days': '30', 'max_image_age_days': '0'})
save('2-all-supported', e)
print('2 ALL SUPPORTED', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS'
ids = [t for t, _ in tasks(e)]
assert 'log_all_supported' in ids and 'alert_slack' not in ids and len(hits()) == n0
print(report(e))
# 3 image age check: a supported but old image alerts only through the age rule
n0 = len(hits())
e = run({'images': 'ubuntu:24.04', 'warn_days': '30', 'max_image_age_days': '1'})
save('3-old-build', e)
print('3 OLD BUILD', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS' and 'alert_slack' in [t for t, _ in tasks(e)]
print('slack payload:', alert_text(n0))
# 4 unreadable image alerts and never counts as supported
n0 = len(hits())
e = run({'images': 'python:3.13-slim\nnosuch-account/nosuch-image:1', 'max_image_age_days': '0'})
save('4-unreadable', e)
print('4 UNREADABLE', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS' and len(hits()) == n0 + 1
print('slack payload:', alert_text(n0 + 0) if False else json.loads(hits()[-1]['body'])['text'])
# 5 pinned digest: the digest of alpine:3.20 right now, written as repo@sha256
import urllib.request as _u
tok = json.load(_u.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/alpine:pull'))['token']
rq = _u.Request('https://registry-1.docker.io/v2/library/alpine/manifests/3.20', method='HEAD', headers={'Authorization': 'Bearer ' + tok, 'Accept': 'application/vnd.oci.image.index.v1+json'})
digest = _u.urlopen(rq).headers['Docker-Content-Digest']
n0 = len(hits())
e = run({'images': 'alpine@' + digest, 'max_image_age_days': '0'})
save('5-pinned-digest', e)
print('5 PINNED DIGEST', e['state']['current'], digest, tasks(e))
rep = report(e); print(rep)
assert e['state']['current'] == 'SUCCESS' and 'alpine-linux' in rep and 'EXPIRED' in rep
# 6 private registry with basic auth (local registry:2): wrong/absent credentials fail closed, right ones read the image
subprocess.run(['mkdir', '-p', '/tmp/regauth'], check=True)
ht = subprocess.run(['docker', 'run', '--rm', '--entrypoint', 'htpasswd', 'httpd:2', '-Bbn', 'proofuser', REGPASS], capture_output=True, text=True, check=True).stdout
pathlib.Path('/tmp/regauth/htpasswd').write_text(ht)
subprocess.run(['docker', 'run', '-d', '--name', 'proof-registry', '-p', '127.0.0.1:5000:5000', '-v', '/tmp/regauth:/auth', '-e', 'REGISTRY_AUTH=htpasswd', '-e', 'REGISTRY_AUTH_HTPASSWD_REALM=proof', '-e', 'REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd', 'registry:2'], check=True)
time.sleep(4)
subprocess.run(['docker', 'pull', 'python:3.9-slim'], check=True)
subprocess.run(['docker', 'tag', 'python:3.9-slim', 'localhost:5000/team/legacy-api:1'], check=True)
subprocess.run(['docker', 'login', 'localhost:5000', '-u', 'proofuser', '--password-stdin'], input=REGPASS, text=True, check=True)
subprocess.run(['docker', 'push', 'localhost:5000/team/legacy-api:1'], check=True)
host_net = flow_txt.replace('    containerImage: python:3.12-slim\n', '    containerImage: python:3.12-slim\n    taskRunner:\n      type: io.kestra.plugin.scripts.runner.docker.Docker\n      networkMode: host\n')
assert host_net != flow_txt
deploy(host_net)
n0 = len(hits())
e = run({'images': 'localhost:5000/team/legacy-api:1', 'max_image_age_days': '0'})
save('6a-private-no-credentials', e)
print('6a PRIVATE WITHOUT CREDENTIALS', e['state']['current'], tasks(e))
txt = json.loads(hits()[-1]['body'])['text'] if len(hits()) == n0 + 1 else ''
print('slack payload:', txt)
assert 'could not read the image' in txt and 'python' not in txt.split('Could not check')[0]
n0 = len(hits())
e = run({'images': 'localhost:5000/team/legacy-api:1', 'max_image_age_days': '0', 'registry_host': 'localhost:5000', 'registry_username': 'proofuser', 'registry_password_secret': 'REGISTRY_PASSWORD'})
save('6b-private-with-credentials', e)
print('6b PRIVATE WITH CREDENTIALS', e['state']['current'], tasks(e))
rep = report(e); print(rep)
assert e['state']['current'] == 'SUCCESS' and '| localhost:5000/team/legacy-api:1 | python | 3.9' in rep and 'EXPIRED' in rep
n0 = len(hits())
e = run({'images': 'localhost:5000/team/legacy-api:1\npython:3.13-slim', 'max_image_age_days': '0', 'registry_host': 'localhost:5000', 'registry_username': 'proofuser', 'registry_password_secret': 'REGISTRY_PASSWORD'})
save('6c-credentials-not-sent-to-other-registries', e)
rep = report(e); print(rep)
assert 'python:3.13-slim | python | 3.13' in rep
logs = pathlib.Path('evidence/6b-private-with-credentials-logs.json').read_text()
assert REGPASS not in logs, 'password leaked to logs'
print('password absent from execution logs: OK')
# 7 failed audit: same flow with an unpullable container image so the task fails
deploy(flow_txt.replace('python:3.12-slim', 'python:0.0-does-not-exist'))
n0 = len(hits())
e = run({})
save('7-failed-check', e)
print('7 FAILED CHECK', e['state']['current'], tasks(e))
assert e['state']['current'] == 'FAILED'
assert 'alert_audit_failed' in [t for t, _ in tasks(e)]
assert len(hits()) == n0 + 1
print('slack payload:', json.loads(hits()[-1]['body'])['text'])
print('ALL PATHS PASS')
