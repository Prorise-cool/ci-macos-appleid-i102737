#!/usr/bin/env python3
"""Discovery: are any public free-SMS inboxes readable (incl. Apple SMS)?
Uses the already-running safaridriver (headful Safari) to load pages, then reads
document body text and performance resource entries to discover the inbox API.
Read-only; no codes guessed; nothing sent."""
import os, re, json, time, base64, urllib.request, urllib.error
OUT = os.path.dirname(os.path.abspath(__file__)) + '/out'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'discover.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': []}
def ev(k, v): STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:1500])
def save(): json.dump(STATE, open(os.path.join(OUT, 'discover.json'), 'w'), indent=2, ensure_ascii=False)

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
def http(url, timeout=30):
    req = urllib.request.Request(url); req.add_header('User-Agent', UA)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        return r.status, r.read()

WD = 'http://127.0.0.1:4444'; SID = None
def wd(method, path, data=None, timeout=120):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(WD + path, data=body, method=method); req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
            t = r.read().decode(errors='replace')
            try: return json.loads(t)
            except Exception: return {'raw': t}
    except urllib.error.HTTPError as e:
        t = e.read().decode(errors='replace')
        try: return json.loads(t)
        except Exception: return {'raw': t, 'code': e.code}
def sess(): return '/session/%s' % SID
def js(s, a=None): return wd('POST', sess() + '/execute/sync', {'script': s, 'args': a or []}).get('value')
def nav(url):
    wd('POST', sess() + '/url', {'url': url})

def probe_page(tag, url, wait=8):
    ev('probe', {'tag': tag, 'url': url})
    try: nav(url)
    except Exception as e: ev('nav_err', {'tag': tag, 'err': repr(e)[:200]}); return
    time.sleep(wait)
    try: txt = js('return document.body?document.body.innerText.slice(0,12000):"";') or ''
    except Exception as e: txt = ''; ev('txt_err', repr(e)[:150])
    open(os.path.join(OUT, tag + '.txt'), 'w').write(txt)
    try: perf = js("return performance.getEntriesByType('resource').map(function(e){return e.name;}).filter(function(n){return /api|sms|number|message/i.test(n);});") or []
    except Exception as e: perf = []; ev('perf_err', repr(e)[:150])
    ev('perf', {'tag': tag, 'urls': perf[:40]})
    open(os.path.join(OUT, tag + '.perf.json'), 'w').write(json.dumps(perf, indent=1))
    six = re.findall(r'(?<!\d)(\d{6})(?!\d)', txt)
    ev('text_stats', {'tag': tag, 'len': len(txt), 'apple': 'apple' in txt.lower(), 'sixdigit': six[:8], 'head': txt[:400]})
    # fetch any API urls that look like message endpoints directly
    for u in perf[:40]:
        if not re.search(r'(sms|messages|numbers)', u, re.I): continue
        try:
            st, b = http(u, timeout=25)
            ev('api_fetch', {'tag': tag, 'url': u, 'status': st, 'bytes': len(b), 'body_head': b[:600].decode(errors='replace')})
        except Exception as e:
            ev('api_fetch_err', {'url': u, 'err': repr(e)[:150]})

def main():
    global SID
    ev('stage', 'start')
    r = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'safari'}}})
    SID = (r.get('value', {}) or {}).get('sessionId')
    ev('wd_session', SID)
    if not SID: save(); return
    wd('POST', sess() + '/window/maximize', {})
    targets = [
        ('q_us', 'https://quackr.io/temporary-numbers/united-states'),
        ('q_17019976600', 'https://quackr.io/temporary-numbers/united-states/17019976600'),
        ('q_17759802006', 'https://quackr.io/temporary-numbers/united-states/17759802006'),
        ('q_17759865200', 'https://quackr.io/temporary-numbers/united-states/17759865200'),
        ('anon_home', 'https://anonymsms.com/'),
        ('rsmss_home', 'https://receive-smss.com/'),
        ('receivesms_co', 'https://receivesms.co/'),
    ]
    for tag, url in targets:
        try: probe_page(tag, url)
        except Exception as e: ev('probe_fatal', {'tag': tag, 'err': repr(e)[:300]})
        save()
    try: wd('DELETE', sess())
    except Exception: pass
    save()
if __name__ == '__main__':
    try: main()
    except Exception:
        import traceback; ev('fatal', traceback.format_exc()[-2000:]); save()
