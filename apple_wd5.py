#!/usr/bin/env python3
"""Run 5: fresh Apple Account creation in real Safari using phone +1 587 405 6545,
whose public inbox (receivesms.co/ca-phone-number/23253) we can read from the runner.
Flow: form -> image captcha (Vision OCR) -> email code from our own mail.tm mailbox ->
phone verification stage -> poll the public inbox for a NEW Apple SMS (never guess/brute)
-> if an Apple code really arrives, fill it once and record the next stage verbatim."""
import os, re, json, time, random, string, traceback, base64, subprocess
import urllib.request, urllib.error

OUT = os.path.dirname(os.path.abspath(__file__)) + '/out5'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run5.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': [], 'stage': 'init'}
def save(): json.dump(STATE, open(os.path.join(OUT, 'summary5.json'), 'w'), indent=2, ensure_ascii=False)
def ev(k, v): STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:2000]); save()

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
INBOX = 'https://receivesms.co/ca-phone-number/23253/'
T0 = time.time()

def http(url, data=None, headers=None, timeout=35):
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET'); req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items(): req.add_header(k, v)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r: return r.status, r.read()

def strip_tags(s): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()

def parse_inbox(html):
    msgs = []
    for art in re.split(r'<article class="entry-card', html)[1:]:
        m_from = re.search(r'class="from-link"[^>]*>([^<]+)<', art)
        m_code = re.search(r'class="code"[^>]*data-code="(\d{4,8})"', art)
        m_time = re.search(r'<span class="muted">([^<]+)</span>', art)
        m_body = re.search(r'<div class="entry-body">(.*?)</div>\s*</article>', art, re.S)
        body = strip_tags(m_body.group(1)) if m_body else ''
        msgs.append({'from': (m_from.group(1).strip() if m_from else ''), 'code': (m_code.group(1) if m_code else ''),
                     'time': (m_time.group(1).strip() if m_time else ''), 'text': body[:800]})
    return msgs

def fetch_inbox():
    st, b = http(INBOX + '?t=%d' % int(time.time()), headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    html = b.decode('utf-8', 'replace')
    return st, parse_inbox(html), html

def msg_key(m): return (m['from'], m['text'][:300], m['time'])

def mailtm_new():
    st, b = http('https://api.mail.tm/domains'); domain = json.loads(b)['hydra:member'][0]['domain']
    pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
    addr = 'x%s%d@%s' % (int(time.time()) % 100000, random.randint(10, 99), domain)
    http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
    st2, b2 = http('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
    STATE['email'] = {'addr': addr, 'pw': pw, 'token': json.loads(b2).get('token')}
    ev('mailtm', {'addr': addr, 'token': bool(STATE['email']['token'])})

def mail_wait_code(secs=170):
    e = STATE['email']; end = time.time() + secs
    while time.time() < end:
        try:
            st, b = http('https://api.mail.tm/messages', headers={'Authorization': 'Bearer ' + e['token']})
            msgs = json.loads(b).get('hydra:member', [])
            if msgs:
                st2, b2 = http('https://api.mail.tm/messages/' + msgs[0]['id'], headers={'Authorization': 'Bearer ' + e['token']})
                j = json.loads(b2); txt = (j.get('text') or '') + ' ' + json.dumps(j.get('html') or [], ensure_ascii=False)[:4000]
                open(os.path.join(OUT, 'email_full.json'), 'w').write(json.dumps(j, ensure_ascii=False)[:20000])
                codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', txt)
                ev('mail_code', {'subject': j.get('subject'), 'codes': codes[:5]})
                if codes: return codes[0]
        except Exception as ex: ev('mail_err', repr(ex)[:150])
        time.sleep(8)
    return None

def norm_phone(s):
    d = re.sub(r'\D', '', s or '')
    if len(d) == 11 and d.startswith('1'): d = d[1:]
    return d
NUMBER = norm_phone(os.environ.get('APPLE_PHONE', '15874056545'))
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
def body_text(): return js('return document.body?document.body.innerText.slice(0,9000):"";') or ''
def shot(n):
    v = wd('GET', sess() + '/screenshot').get('value')
    if isinstance(v, str) and v: open(os.path.join(OUT, n + '.png'), 'wb').write(base64.b64decode(v))
def dump(n):
    t = body_text(); open(os.path.join(OUT, n + '.txt'), 'w').write(t); open(os.path.join(OUT, n + '.html'), 'w').write(source()[:600000]); shot(n)
    log('===', n, 'len=', len(t)); log(t[:700]); return t
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
def set_select_name(name, value):
    ok = js("""var s=document.querySelector('select[name="%s"]'); if(!s) return 'nosel';
      var has=Array.from(s.options).some(function(o){return o.value===arguments[0];}); if(!has) return 'noopt';
      s.value=arguments[0]; s.dispatchEvent(new Event('input',{bubbles:true})); s.dispatchEvent(new Event('change',{bubbles:true})); return s.value;""" % name, [value])
    return ok
def captcha_img():
    src = js("var i=document.querySelector('.captcha img.img'); return i?i.src:null;")
    if not src: return None
    p = os.path.join(OUT, 'captcha.jpg')
    if src.startswith('data:image'): open(p, 'wb').write(base64.b64decode(src.split(',', 1)[1])); return p
    st, b = http(src); open(p, 'wb').write(b); return p
def ocr(p):
    try:
        out = subprocess.run(['/tmp/ocr', p], capture_output=True, text=True, timeout=120).stdout.strip()
        ev('ocr_raw', out[-800:])
        m = re.search(r'BEST:(.*)$', out, re.M); return (m.group(1) if m else '').strip()
    except Exception as e: ev('ocr_err', repr(e)[:200]); return ''
def new_code():
    el = find_xp('//button[@aria-label="New Code"]') or find_xp('//button[.//span[contains(@class,"new-code")]]')
    if el: click(el); return True
    return False
def fill_code(digits):
    els = js("return Array.from(document.querySelectorAll('input.form-security-code-input')).length;") or 0
    ev('code_inputs', els)
    for i, d in enumerate(digits[:els or 0], start=1):
        el = find_xp('(//input[contains(@class,"form-security-code-input")])[%d]' % i)
        if el:
            try: click(el)
            except Exception: pass
            keys(el, d)
    vals = js("return Array.from(document.querySelectorAll('input.form-security-code-input')).map(function(e){return e.value;}).join('');")
    ev('code_values', vals)
    return vals

def poll_inbox_for_apple(baseline, secs=800):
    base = set(msg_key(m) for m in baseline)
    end = time.time() + secs; n = 0; seen_new = []
    while time.time() < end:
        if time.time() - T0 > 23 * 60:
            ev('poll_stop_budget', round(time.time() - T0)); break
        n += 1
        try:
            st, msgs, html = fetch_inbox()
            new = [m for m in msgs if msg_key(m) not in base]
            if new:
                ev('inbox_new_%d' % n, {'status': st, 'count': len(new), 'msgs': new[:8]})
                for m in new:
                    if msg_key(m) in [msg_key(x) for x in seen_new]: continue
                    seen_new.append(m)
                # Apple-style match: body mentions apple / verification, and has a 6-digit code
                for m in new:
                    low = m['text'].lower()
                    code = m['code'] or ''
                    if not code:
                        c = re.search(r'(?<!\d)(\d{6})(?!\d)', m['text'])
                        code = c.group(1) if c else ''
                    if code and ('apple' in low or 'verification' in low or 'code' in low):
                        ev('apple_sms_found', m)
                        return m
            else:
                log('poll', n, 'no new msgs (total', len(msgs), ')')
        except Exception as ex:
            ev('poll_err', repr(ex)[:200])
        time.sleep(40)
    ev('poll_timeout', {'polls': n, 'new_seen': seen_new[:10]})
    return None

def main():
    ev('stage', 'start'); ev('number', NUMBER)
    try:
        st, msgs, html = fetch_inbox()
        STATE['inbox_baseline'] = msgs[:25]; ev('inbox_baseline', {'status': st, 'count': len(msgs), 'first': msgs[:3]})
        open(os.path.join(OUT, 'inbox_baseline.html'), 'w').write(html[:400000])
    except Exception as ex:
        ev('inbox_baseline_err', repr(ex)[:300]); msgs = []
    mailtm_new()
    r = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'safari'}}}); globals()['SID'] = (r.get('value', {}) or {}).get('sessionId')
    ev('wd_session', SID)
    if not SID: STATE['stage'] = 'no_session'; save(); return
    wd('POST', sess() + '/window/maximize', {})
    wd('POST', sess() + '/url', {'url': 'https://account.apple.com/account#/create'}); time.sleep(8)
    fe = find('#aid-create-widget-iFrame')
    if not fe: dump('10_noiframe'); STATE['stage'] = 'no_iframe'; save(); return
    switch_frame(fe); time.sleep(3); dump('12_form')
    email = STATE['email']['addr']; pw = STATE['password'] = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(13))
    for nm, v in (('firstName', 'Alex'), ('lastName', 'Miller')): set_input(nm, v)
    set_tid('select-month', '04'); set_tid('select-day', '09'); set_tid('select-year', '1990')
    set_input('appleId', email); set_input('password', pw); set_input('confirmPassword', pw)
    pc = set_select_name('phoneCode', 'CA'); ev('phoneCode_set', pc)
    set_input('phoneNumber', NUMBER)
    ev('phone_validity', js("var e=document.querySelector('input[name=phoneNumber]'); return e?{v:e.value,ok:e.checkValidity(),msg:e.validationMessage}:null;"))
    dump('13_filled')
    ok_submit = False
    for attempt in range(1, 4):
        for imgtry in range(1, 3):
            p = captcha_img()
            if not p: break
            txt = ocr(p); g = re.sub(r'[^A-Za-z0-9]', '', txt)
            ev('ocr_guess', {'attempt': attempt, 'img': imgtry, 'text': txt})
            if len(g) >= 4:
                el = find('input[name="captcha"]')
                if el:
                    try: click(el); keys(el, g)
                    except Exception: pass
                break
            if imgtry < 2: new_code(); time.sleep(4)
        btn = find_xp('//button[@type="submit"]')
        if btn: click(btn)
        time.sleep(9); t = dump('2%d_after_submit_%d' % (attempt, attempt)); low = t.lower()
        if 'verification code' in low or js("return document.querySelectorAll('input.form-security-code-input').length;"):
            ok_submit = True; break
        if 'challenge' in low or 'incorrect' in low: new_code(); time.sleep(4); continue
        ev('submit_blocked', t[:800]); break
    if not ok_submit: STATE['stage'] = 'no_email_stage'; save(); return
    STATE['stage'] = 'email_code_stage'; save(); dump('30_email_code_stage')
    code = mail_wait_code(170)
    if not code: STATE['stage'] = 'email_code_missing'; save(); return
    STATE['email_code'] = code; save()
    fill_code(code); dump('31_code_filled')
    btn = find_xp('//button[@type="submit"]') or find_xp('//button[contains(normalize-space(.),"Continue")]')
    if btn: click(btn)
    time.sleep(10); t = dump('40_after_email_code'); low = t.lower()
    errs = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);""")
    ev('errors_after_email_code', errs)
    ev('final_url', js('return location.href'))
    if 'phone' in low and 'code' in low: STATE['stage'] = 'phone_verification_stage'; save()
    elif 'verify your email' in low: STATE['stage'] = 'email_code_rejected'; save()
    else: STATE['stage'] = 'post_email_stage'; save()
    if STATE['stage'] != 'phone_verification_stage':
        try: wd('DELETE', sess())
        except Exception: pass
        return
    dump('50_phone_stage')
    # baseline re-capture immediately before judging delivery (form submit already triggered SMS)
    try:
        st2, msgs2, html2 = fetch_inbox(); ev('inbox_baseline2', {'status': st2, 'count': len(msgs2), 'first': msgs2[:3]})
        if msgs2: msgs = msgs2
    except Exception as ex: ev('inbox_baseline2_err', repr(ex)[:200])
    found = poll_inbox_for_apple(msgs, secs=800)
    if not found:
        STATE['stage'] = 'phone_sms_not_received'; save(); dump('60_sms_timeout')
        try: wd('DELETE', sess())
        except Exception: pass
        return
    STATE['sms_found'] = found; save()
    digits = found['code'] or (re.search(r'(?<!\d)(\d{6})(?!\d)', found['text']) or [None, ''])[1]
    if not digits or len(digits) != 6:
        STATE['stage'] = 'sms_code_unparsable'; save(); return
    fill_code(digits); dump('61_phone_code_filled')
    btn = find_xp('//button[@type="submit"]') or find_xp('//button[contains(normalize-space(.),"Continue")]') or find_xp('//button[contains(normalize-space(.),"Verify")]')
    if btn: click(btn)
    time.sleep(10); t = dump('70_after_phone_code'); low = t.lower()
    errs = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);""")
    ev('errors_after_phone_code', errs)
    ev('final_url_after_phone', js('return location.href'))
    if 'phone' in low and 'code' in low: STATE['stage'] = 'phone_code_rejected'; save()
    elif 'terms' in low or 'agree' in low: STATE['stage'] = 'terms_stage'; save()
    elif 'welcome' in low or 'account' in low: STATE['stage'] = 'post_phone_stage'; save()
    else: STATE['stage'] = 'post_phone_unknown'; save()
    try: wd('DELETE', sess())
    except Exception: pass

if __name__ == '__main__':
    try: main()
    except Exception:
        ev('fatal', traceback.format_exc()[-2500:]); STATE['stage'] = 'exception'; save()
