#!/usr/bin/env python3
"""Run 2: real Safari on macOS runner -> fill Apple 'Create Your Apple Account' form,
solve the image challenge with Apple's own Vision OCR (compiled separately), submit once or twice.
Never guesses any SMS/2FA code."""
import os, re, json, time, random, string, sys, traceback, base64, subprocess
import urllib.request, urllib.error
OUT = os.path.dirname(os.path.abspath(__file__)) + '/out'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run2.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': [], 'stage': 'init'}
def ev(k, v): STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:1500]); save()
def save(): json.dump(STATE, open(os.path.join(OUT, 'summary2.json'), 'w'), indent=2, ensure_ascii=False)

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
def http(url, data=None, headers=None, timeout=35):
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items(): req.add_header(k, v)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r: return r.status, r.read()

def mailtm_new():
    try:
        st, b = http('https://api.mail.tm/domains'); doms = json.loads(b)['hydra:member']
        domain = doms[0]['domain']; pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
        addr = 'v%s%d@%s' % (int(time.time()) % 100000, random.randint(10, 99), domain)
        http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
        st2, b2 = http('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
        STATE['email'] = {'addr': addr, 'pw': pw, 'token': json.loads(b2).get('token')}; ev('mailtm', {'addr': addr, 'token': bool(STATE['email']['token'])})
    except Exception as e: ev('mailtm_err', repr(e)[:300])

def norm_phone(s):
    d = re.sub(r'\D', '', s or '')
    if len(d) == 11 and d.startswith('1'): d = d[1:]
    return d
NUMBER = norm_phone(os.environ.get('APPLE_PHONE', '2833523739'))

WD = 'http://127.0.0.1:4444'; SID = None
def wd(method, path, data=None, timeout=120):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(WD + path, data=body, method=method); req.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
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
    return None
def find(css):
    return ekey(wd('POST', sess() + '/element', {'using': 'css selector', 'value': css}).get('value', {}))
def find_xp(xp):
    return ekey(wd('POST', sess() + '/element', {'using': 'xpath', 'value': xp}).get('value', {}))
def click(el): return wd('POST', sess() + '/element/%s/click' % el, {})
def keys(el, text): return wd('POST', sess() + '/element/%s/value' % el, {'text': text})
def js(script, args=None): return wd('POST', sess() + '/execute/sync', {'script': script, 'args': args or []}).get('value')
def source(): return wd('GET', sess() + '/source').get('value', '') or ''
def body_text(): return js('return document.body ? document.body.innerText.slice(0,8000) : "";') or ''
def shot(name):
    r = wd('GET', sess() + '/screenshot'); v = r.get('value')
    if isinstance(v, str) and v: open(os.path.join(OUT, name + '.png'), 'wb').write(base64.b64decode(v))
def dump(name):
    t = body_text(); open(os.path.join(OUT, name + '.txt'), 'w').write(t); open(os.path.join(OUT, name + '.html'), 'w').write(source()[:500000]); shot(name)
    log('===', name, 'len=', len(t)); log(t[:800]); return t

def new_session():
    global SID
    r = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'safari'}}})
    SID = (r.get('value', {}) or {}).get('sessionId')
    ev('wd_session', SID or r); return bool(SID)

def goto(url): return wd('POST', sess() + '/url', {'url': url})
def switch_frame(el):
    return wd('POST', sess() + '/frame', {'id': {'element-6066-11e4-a52e-4f735466cecf': el}})

def set_input(name, value):
    """set value through real key events; verify"""
    el = find('input[name="%s"]' % name)
    if not el: return ('missing', name)
    cur = js('var e=document.querySelector(arguments[0]); return e?e.value:null;', ['input[name="%s"]' % name])
    if cur: return ('already', name)
    try: click(el)
    except Exception: pass
    keys(el, value)
    v = js('var e=document.querySelector(arguments[0]); return e?e.value:null;', ['input[name="%s"]' % name])
    return ('ok' if v else 'no_value', name)

def set_select_by_testid(tid, value):
    ok = js("""var s=document.querySelector('[data-testid="%s"]'); if(!s) return 'nosel';
      s.value=arguments[0]; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true}));
      var lab=s.parentNode.querySelector('.form-dropdown-label'); if(lab){var o=s.options[s.selectedIndex]; if(o) lab.textContent=o.text;}
      return s.value;""" % tid, [value])
    return ('ok' if ok == value else 'bad', tid, value, str(ok))

def set_select_by_name(name, value):
    ok = js("""var s=document.querySelector('select[name="%s"]'); if(!s) return 'nosel';
      s.value=arguments[0]; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true}));
      return s.value;""" % name, [value])
    return ('ok' if ok == value else 'bad', name, value, str(ok))

def captcha_img():
    src = js("var i=document.querySelector('.captcha img.img'); return i?i.src:null;")
    if not src: return None
    if src.startswith('data:image'):
        b = base64.b64decode(src.split(',', 1)[1]); p = os.path.join(OUT, 'captcha.jpg'); open(p, 'wb').write(b); return p
    try:
        st, b = http(src); p = os.path.join(OUT, 'captcha.jpg'); open(p, 'wb').write(b); return p
    except Exception as e:
        ev('captcha_dl_err', repr(e)[:200]); return None

def ocr(path):
    for exe in ('/tmp/ocr', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ocr')):
        if os.path.exists(exe):
            try:
                out = subprocess.run([exe, path], capture_output=True, text=True, timeout=60).stdout.strip()
                return out
            except Exception as e:
                return 'OCRBIN_ERR ' + repr(e)[:120]
    return 'NO_OCR_BIN'

def click_new_code():
    el = find_xp('//button[.//span[contains(@class,"new-code")] or @aria-label="New Code"]')
    if el: click(el); return True
    return False

def main():
    ev('stage', 'start')
    mailtm_new()
    if not new_session(): STATE['stage'] = 'no_session'; save(); return
    ev('window', wd('POST', sess() + '/window/maximize', {}))
    goto('https://account.apple.com/account#/create'); time.sleep(8)
    dump('10_landing')
    fe = find('#aid-create-widget-iFrame')
    if not fe:
        el = find_xp('//a[contains(normalize-space(.),"Create Your Apple")]') or find_xp('//*[contains(text(),"Create Your Apple")]')
        if el: click(el)
        time.sleep(8); dump('11_after_click'); fe = find('#aid-create-widget-iFrame')
    ev('iframe', bool(fe))
    if not fe: STATE['stage'] = 'no_iframe'; save(); return
    switch_frame(fe); time.sleep(3); dump('12_form')
    email = STATE['email']['addr']; pw = STATE['password'] = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(13))
    r = {}
    r['first'] = set_input('firstName', 'Alex'); r['last'] = set_input('lastName', 'Miller')
    r['month'] = set_select_by_testid('select-month', '04')
    r['day'] = set_select_by_testid('select-day', '09')
    r['year'] = set_select_by_testid('select-year', '1990')
    r['email'] = set_input('appleId', email)
    r['password'] = set_input('password', pw); r['confirm'] = set_input('confirmPassword', pw)
    r['phonecode'] = set_select_by_name('phoneCode', 'US'); r['phone'] = set_input('phoneNumber', NUMBER)
    ev('fill', {k: str(v) for k, v in r.items()})
    dump('13_filled')
    vals = js("""var o={}; document.querySelectorAll('input,select').forEach(function(e){var k=e.name||e.getAttribute('data-testid')||''; if(k) o[k]=e.value;}); return o;""")
    ev('values', vals)
    solved = False
    for attempt in range(1, 4):
        p = captcha_img()
        if not p:
            ev('no_captcha', attempt); solved = True; break
        txt = ocr(p)
        ev('ocr', {'attempt': attempt, 'text': txt})
        guess = re.sub(r'[^A-Za-z0-9]', '', txt)
        if not guess or guess.startswith('NO_OCR'):
            ev('ocr_failed', attempt); break
        el = find('input[name="captcha"]')
        if not el: break
        try: click(el); keys(el, guess)
        except Exception: pass
        dump('2%d_before_submit_%d' % (attempt, attempt))
        btn = find_xp('//button[@type="submit"]') or find_xp('//button[contains(normalize-space(.),"Continue")]')
        if btn: click(btn)
        time.sleep(9)
        t = dump('3%d_after_submit_%d' % (attempt, attempt))
        low = t.lower()
        if 'enter a valid phone number' in low or 'phone error' in low:
            v = js("""var e=document.querySelector('input[name=phoneNumber]'); if(!e) return null;
              var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
              s.call(e, arguments[0]); e.dispatchEvent(new Event('input',{bubbles:true})); return e.value;""", [NUMBER])
            ev('phone_refixed', v)
            if attempt < 3:
                click_new_code(); time.sleep(4)
                continue
        if 'security challenge error' in low or 'incorrect' in low or 'try again' in low or "didn't match" in low:
            ev('captcha_wrong', attempt)
            if attempt < 3:
                click_new_code(); time.sleep(4); dump('4%d_newcode_%d' % (attempt, attempt)); continue
            break
        # look for code fields / next stage
        codef = js("""return Array.from(document.querySelectorAll('input')).filter(function(e){
            return /code|otp|security|verification/i.test((e.name||'')+(e.id||'')+(e.getAttribute('aria-label')||'')+(e.placeholder||''));}).map(function(e){return (e.name||'')+'|'+(e.id||'')+'|'+(e.placeholder||'');});""")
        ev('code_fields', codef)
        if codef: STATE['stage'] = 'code_field'; save(); dump('50_code_field'); return
        el_err = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,200);}).filter(Boolean).slice(0,8);""")
        ev('errors_after_submit', el_err)
        STATE['stage'] = 'after_submit'; save()
        break
    STATE['stage'] = STATE.get('stage') or 'end'; save()
    try: ev('final_url', js('return location.href'))
    except Exception: pass
    try: wd('DELETE', sess())
    except Exception: pass

if __name__ == '__main__':
    try: main()
    except Exception:
        ev('fatal', traceback.format_exc()[-2500:]); STATE['stage'] = 'exception'; save(); raise
