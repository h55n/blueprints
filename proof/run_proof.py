import subprocess, os, tarfile, hashlib, shutil, sys, pathlib, base64 as _b64, time as _t, urllib.request as _ur
W = pathlib.Path('/tmp/eolwork'); W.mkdir(exist_ok=True)
pathlib.Path('evidence').mkdir(exist_ok=True)
_ur.urlretrieve('https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jre/hotspot/normal/eclipse', str(W / 'jre.tgz'))
with tarfile.open(W / 'jre.tgz') as t: t.extractall(W / 'jre')
JAVA = str(next((W / 'jre').glob('*/bin/java')))
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
env = dict(os.environ, SECRET_SLACK_WEBHOOK_URL=_b64.b64encode(b'http://127.0.0.1:9999/hook').decode())
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
src = pathlib.Path('flows/runtime-eol-watch.yaml').read_text()
flow_txt = src.split('\nextend:\n')[0] + '\n'
def deploy(text):
    try:
        call('/flows', 'POST', text.encode(), 'application/x-yaml')
    except urllib.error.HTTPError as exc:
        if exc.code in (409, 422):
            call('/flows/company.team/runtime-eol-watch', 'PUT', text.encode(), 'application/x-yaml')
        else:
            raise RuntimeError(exc.read().decode()[:2000])
def run(inputs):
    b = 'kestra-proof-boundary'
    data = ''.join('--' + b + '\r\nContent-Disposition: form-data; name="' + k + '"\r\n\r\n' + v + '\r\n' for k, v in inputs.items()) + '--' + b + '--\r\n'
    e = json.loads(call('/executions/company.team/runtime-eol-watch', 'POST', data.encode(), 'multipart/form-data; boundary=' + b))
    for _ in range(240):
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
summary = {}
# 1 alert path: defaults
deploy(flow_txt)
n0 = len(hits())
e = run({})
save('1-alert', e)
print('1 ALERT', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS'
ids = [t for t, _ in tasks(e)]
assert 'alert_slack' in ids and 'log_all_supported' not in ids
h = hits()[n0:]
assert len(h) == 1, h
print('slack payload:', json.loads(h[0]['body'])['text'])
outputs = json.loads(call('/main/outputs/executions/' + e['id']))
rep = call('/executions/' + e['id'] + '/file?path=' + urllib.request.quote(outputs['report'], safe=''))
out.joinpath('1-alert-report.md').write_bytes(rep); print(rep.decode())
# 2 all supported
n0 = len(hits())
e = run({'runtimes': 'python:3.14\n# comment line\n', 'warn_days': '30'})
save('2-all-supported', e)
print('2 ALL SUPPORTED', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS'
ids = [t for t, _ in tasks(e)]
assert 'log_all_supported' in ids and 'alert_slack' not in ids
assert len(hits()) == n0
# 2b unknown product alerts
n0 = len(hits())
e = run({'runtimes': 'python:3.14\nnotaproduct:1', 'warn_days': '30'})
save('2b-unknown', e)
print('2b UNKNOWN', e['state']['current'], tasks(e))
assert e['state']['current'] == 'SUCCESS' and len(hits()) == n0 + 1
print('slack payload:', json.loads(hits()[-1]['body'])['text'])
# 3 failed check: same flow with an unpullable container image so the check task fails
deploy(flow_txt.replace('python:3.12-slim', 'python:0.0-does-not-exist'))
n0 = len(hits())
e = run({})
save('3-failed-check', e)
print('3 FAILED CHECK', e['state']['current'], tasks(e))
assert e['state']['current'] == 'FAILED'
assert 'alert_check_failed' in [t for t, _ in tasks(e)]
assert len(hits()) == n0 + 1
print('slack payload:', json.loads(hits()[-1]['body'])['text'])
print('ALL PATHS PASS')
