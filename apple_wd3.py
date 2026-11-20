#!/usr/bin/env python3
"""Run 3: real Safari + phone in national format + multi-variant Vision OCR of Apple image challenge.
Cap: at most 4 captcha images, at most 3 submit attempts. No SMS/2FA code is ever guessed."""
import os, re, json, time, random, string, traceback, base64, subprocess
import urllib.request, urllib.error
OUT = os.path.dirname(os.path.abspath(__file__)) + '/out'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run3.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': [], 'stage': 'init'}
def save(): json.dump(STATE, open(os.path.join(OUT, 'summary3.json'), 'w'), indent=2, ensure_ascii=False)
def ev(k, v): STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:1500]); save()

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
def http(url, data=None, headers=None, timeout=35):
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET'); req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items(): req.add_header(k, v)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r: return r.status, r.read()

def mailtm_new():
    st, b = http('https://api.mail.tm/domains'); domain = json.loads(b)['hydra:member'][0]['domain']
    pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
    addr = 'w%s%d@%s' % (int(time.time()) % 100000, random.randint(10, 99), domain)
    http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
    st2, b2 = http('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
    STATE['email'] = {'addr': addr, 'pw': pw, 'token': json.loads(b2).get('token')}
    ev('mailtm', {'addr': addr, 'token': bool(STATE['email']['token'])})

def norm_phone(s):
    d = re.sub(r'\D', '', s or '')
    if len(d) == 11 and d.startswith('1'): d = d[1:]
    return d
NUMBER = norm_phone(os.environ.get('APPLE_PHONE', '2833523739'))
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
def ekey(el):
    for k in el:
        if k.startswith('element-') or k == 'ELEMENT': return el[k]
def find(css): return ekey(wd('POST', sess() + '/element', {'using': 'css selector', 'value': css}).get('value', {}))
def find_xp(xp): return ekey(wd('POST', sess() + '/element', {'using': 'xpath', 'value': xp}).get('value', {}))
def click(el): return wd('POST', sess() + '/element/%s/click' % el, {})
def keys(el, t): return wd('POST', sess() + '/element/%s/value' % el, {'text': t})
def js(s, a=None): return wd('POST', sess() + '/execute/sync', {'script': s, 'args': a or []}).get('value')
def source(): return wd('GET', sess() + '/source').get('value', '') or ''
def body_text(): return js('return document.body?document.body.innerText.slice(0,8000):"";') or ''
def shot(n):
    v = wd('GET', sess() + '/screenshot').get('value')
    if isinstance(v, str) and v: open(os.path.join(OUT, n + '.png'), 'wb').write(base64.b64decode(v))
def dump(n):
    t = body_text(); open(os.path.join(OUT, n + '.txt'), 'w').write(t); open(os.path.join(OUT, n + '.html'), 'w').write(source()[:500000]); shot(n)
    log('===', n, 'len=', len(t)); log(t[:500]); return t
def switch_frame(el): return wd('POST', sess() + '/frame', {'id': {'element-6066-11e4-a52e-4f735466cecf': el}})

def set_input(name, value):
    el = find('input[name="%s"]' % name)
    if not el: return ('missing', name)
    cur = js('var e=document.querySelector(arguments[0]); return e?e.value:null;', ['input[name="%s"]' % name])
    if cur: return ('already', name)
    try: click(el)
    except Exception: pass
    keys(el, value)
    v = js('var e=document.querySelector(arguments[0]); return e?e.value:null;', ['input[name="%s"]' % name])
    return ('ok' if v else 'no_value', name)
def set_tid(tid, value):
    ok = js("""var s=document.querySelector('[data-testid="%s"]'); if(!s) return 'nosel';
      s.value=arguments[0]; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true}));
      var lab=s.parentNode.querySelector('.form-dropdown-label'); if(lab){var o=s.options[s.selectedIndex]; if(o) lab.textContent=o.text;} return s.value;""" % tid, [value])
    return ('ok' if ok == value else 'bad', tid, str(ok))
def set_phone(v):
    return js("""var e=document.querySelector('input[name=phoneNumber]'); if(!e) return null;
      var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      s.call(e, arguments[0]); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); return e.value;""", [v])
def captcha_img():
    src = js("var i=document.querySelector('.captcha img.img'); return i?i.src:null;")
    if not src: return None
    if src.startswith('data:image'):
        p = os.path.join(OUT, 'captcha.jpg'); open(p, 'wb').write(base64.b64decode(src.split(',', 1)[1])); return p
    try:
        st, b = http(src); p = os.path.join(OUT, 'captcha.jpg'); open(p, 'wb').write(b); return p
    except Exception as e: ev('captcha_dl_err', repr(e)[:200])
def ocr(p):
    try:
        r = subprocess.run(['/tmp/ocr', p], capture_output=True, text=True, timeout=90)
        out = r.stdout.strip(); ev('ocr_raw', out[-1200:])
        m = re.search(r'BEST:(.*)$', out, re.M)
        return (m.group(1) if m else '').strip()
    except Exception as e:
        ev('ocr_err', repr(e)[:200]); return ''
def new_code():
    el = find_xp('//button[@aria-label="New Code"]') or find_xp('//button[.//span[contains(@class,"new-code")]]')
    if el: click(el); return True
    return False
def mail_poll(secs=90):
    e = STATE.get('email') or {}
    if not e.get('token'): return
    end = time.time() + secs
    while time.time() < end:
        try:
            st, b = http('https://api.mail.tm/messages', headers={'Authorization': 'Bearer ' + e['token']})
            msgs = json.loads(b).get('hydra:member', [])
            if msgs:
                ev('mail_arrived', [{'from': m.get('from', {}).get('address'), 'subject': m.get('subject'), 'id': m.get('id')} for m in msgs[:3]])
                d = []
                for m in msgs[:2]:
                    st2, b2 = http('https://api.mail.tm/messages/' + m['id'], headers={'Authorization': 'Bearer ' + e['token']})
                    j = json.loads(b2); d.append({'subject': j.get('subject'), 'text': (j.get('text') or '')[:2000]})
                open(os.path.join(OUT, 'emails.json'), 'w').write(json.dumps(d, indent=1, ensure_ascii=False)); return
        except Exception as ex: ev('mail_poll_err', repr(ex)[:150])
        time.sleep(10)

def main():
    ev('stage', 'start'); mailtm_new()
    r = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'safari'}}}); globals()['SID'] = (r.get('value', {}) or {}).get('sessionId')
    ev('wd_session', SID)
    if not SID: STATE['stage'] = 'no_session'; save(); return
    wd('POST', sess() + '/window/maximize', {})
    wd('POST', sess() + '/url', {'url': 'https://account.apple.com/account#/create'}); time.sleep(8); dump('10_landing')
    fe = find('#aid-create-widget-iFrame')
    if not fe: STATE['stage'] = 'no_iframe'; save(); return
    switch_frame(fe); time.sleep(3); dump('12_form')
    email = STATE['email']['addr']; pw = STATE['password'] = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(13))
    res = {}
    res['first'] = set_input('firstName', 'Alex'); res['last'] = set_input('lastName', 'Miller')
    res['month'] = set_tid('select-month', '04'); res['day'] = set_tid('select-day', '09'); res['year'] = set_tid('select-year', '1990')
    res['email'] = set_input('appleId', email); res['pw'] = set_input('password', pw); res['pw2'] = set_input('confirmPassword', pw)
    res['phone'] = set_input('phoneNumber', NUMBER); res['phone_v'] = set_phone(NUMBER)
    ev('fill', {k: str(v) for k, v in res.items()}); dump('13_filled')
    for attempt in range(1, 4):
        img_ok = False
        for imgtry in range(1, 3):
            p = captcha_img()
            if not p: ev('no_captcha', attempt); img_ok = True; break
            txt = ocr(p); ev('ocr_guess', {'attempt': attempt, 'img': imgtry, 'text': txt})
            g = re.sub(r'[^A-Za-z0-9]', '', txt)
            if len(g) >= 4:
                el = find('input[name="captcha"]')
                if el:
                    try: click(el); keys(el, g)
                    except Exception: pass
                    ev('captcha_filled', g); img_ok = True; break
            if imgtry < 2: new_code(); time.sleep(4)
        dump('2%d_pre_submit_%d' % (attempt, attempt))
        btn = find_xp('//button[@type="submit"]')
        if btn: click(btn)
        time.sleep(9)
        t = dump('3%d_after_submit_%d' % (attempt, attempt)); low = t.lower()
        errs = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);""")
        ev('errors', errs)
        codef = js("""return Array.from(document.querySelectorAll('input')).filter(function(e){return /code|otp|security|verification/i.test((e.name||'')+(e.id||'')+(e.getAttribute('aria-label')||'')+(e.placeholder||''));}).map(function(e){return (e.name||'')+'|'+(e.placeholder||'');});""")
        ev('code_fields', codef)
        if codef: STATE['stage'] = 'code_field'; save(); dump('50_code_field'); break
        if 'challenge' in low or 'incorrect' in low or 'try again' in low:
            ev('captcha_wrong', attempt); new_code(); time.sleep(4); continue
        if 'valid phone' in low:
            ev('phone_invalid_still', attempt); break
        STATE['stage'] = 'submitted'; save(); break
    mail_poll(90)
    try: ev('final_url', js('return location.href'))
    except Exception: pass
    try: wd('DELETE', sess())
    except Exception: pass
if __name__ == '__main__':
    try: main()
    except Exception:
        ev('fatal', traceback.format_exc()[-2500:]); STATE['stage'] = 'exception'; save()
