import json
from pathlib import Path

raw = json.loads(Path('lychee.json').read_text())
confirmed, uncertain = [], []
for source, entries in raw.get('error_map', {}).items():
    for entry in entries:
        status = entry.get('status', {})
        code = status.get('code')
        text = status.get('text', '')
        item = {'source': source, 'url': entry['url'], 'status': text, 'line': entry.get('span', {}).get('line')}
        # Only explicit absence is actionable. Auth, throttling and server/network
        # errors need a later check, not a declaration that the link is dead.
        if code in (404, 410) or (entry['url'].startswith('file:') and 'File not found' in text):
            confirmed.append(item)
        else:
            uncertain.append(item)
for source, entries in raw.get('timeout_map', {}).items():
    for entry in entries:
        uncertain.append({'source': source, 'url': entry['url'], 'status': 'timeout', 'line': entry.get('span', {}).get('line')})
report = {'checked': raw.get('total', 0), 'successful': raw.get('successful', 0), 'excluded': raw.get('excludes', 0), 'needs_fix': confirmed, 'needs_recheck': uncertain}
confirmed.sort(key=lambda x:(x['source'],x['line'] or 0,x['url']))
uncertain.sort(key=lambda x:(x['source'],x['line'] or 0,x['url']))
Path('link-audit.json').write_text(json.dumps(report, indent=2))
lines = ['# Markdown link audit', '', f"Checked: {report['checked']}; successful: {report['successful']}; excluded: {report['excluded']}", '', '## Links to inspect (HTTP 404/410 or missing local files)' ]
for title, items in [('Links to inspect', confirmed), ('Needs a recheck (not labelled broken)', uncertain)]:
    if title != 'Links to inspect': lines += ['', '## ' + title]
    lines.extend(f"- {x['source']}:{x['line']}: {x['url']} ({x['status']})" for x in items)
    if not items: lines.append('- None')
Path('link-audit.md').write_text('\n'.join(lines) + '\n')
print('::' + json.dumps({'outputs': {'missing_count': len(confirmed), 'recheck_count': len(uncertain), 'checked_count': report['checked']}}) + '::')
