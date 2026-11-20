#!/usr/bin/env python3
"""Drive real Safari (headful, GUI session) on a macOS runner via safaridriver (W3C WebDriver).
Goal: attempt Apple Account creation and record verbatim whether Apple lets it through.
No verification code is ever guessed; only public inboxes are read once."""
import os, re, json, time, random, string, sys, traceback, base64
import urllib.request, urllib.error

OUT = os.path.dirname(os.path.abspath(__file__)) + '/out'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': [], 'stage': 'init'}
def ev(k, v):
    STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:1000])
def save():
    json.dump(STATE, open(os.path.join(OUT, 'summary.json'), 'w'), indent=2, ensure_ascii=False)

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
def http(url, data=None, headers=None, timeout=35):
    req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
    req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items(): req.add_header(k, v)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r:
        return r.status, r.read()

# ---------- email ----------
def mailtm_new():
    try:
        st, b = http('https://api.mail.tm/domains'); doms = json.loads(b)['hydra:member']
        domain = doms[0]['domain']; pw = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
        addr = 'a%s%d@%s' % (int(time.time()) % 10000, random.randint(100, 999), domain)
        st, b = http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
        st2, b2 = http('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'})
        tok = json.loads(b2).get('token')
        STATE['email'] = {'addr': addr, 'pw': pw, 'token': tok}
        ev('mailtm', {'stmt': st, 'token_stmt': st2, 'addr': addr}); save(); return
    except Exception as e:
        ev('mailtm_err', repr(e)[:300])

# ---------- public sms numbers ----------
SMS_SITES = [('receive-smss', 'https://receive-smss.com/'), ('smsreceivefree', 'https://smsreceivefree.com/'),
             ('receivesms.co', 'https://receivesms.co/'), ('anonymsms', 'https://anonymsms.com/'),
             ('sms-online', 'https://sms-online.co/'), ('quackr', 'https://quackr.io/')]
def pub_numbers():
    found = []
    for name, url in SMS_SITES:
        try:
            st, b = http(url, timeout=25); html = b.decode(errors='ignore')
            open(os.path.join(OUT, 'sms_%s.html' % name), 'wb').write(b)
            cands = []
            for m in re.finditer(r'(?:\+1[\s\-\.]?)?\(?([2-9]\d{2})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})', html):
                n = '+1' + m.group(1) + m.group(2) + m.group(3)
                if n not in cands: cands.append(n)
            ev('sms_site', {'site': name, 'status': st, 'bytes': len(html), 'n': len(cands), 'first': cands[:3]})
            if cands: found.append({'site': name, 'url': url, 'number': cands[0], 'first': cands[:5]})
        except Exception as e:
            ev('sms_site_err', {'site': name, 'err': repr(e)[:200]})
    STATE['numbers'] = found; save()

def inbox_probe(entry):
    try:
        st, b = http(entry['url'], timeout=25); html = b.decode(errors='ignore')
        open(os.path.join(OUT, 'inbox_%s.html' % re.sub(r'\W', '_', entry['site'])), 'wb').write(b)
        codes = sorted(set(re.findall(r'(?<![\d])(\d{6})(?![\d])', html)))
        ev('inbox_probe', {'site': entry['site'], 'status': st, 'bytes': len(html), 'apple_word': 'apple' in html.lower(),
                           'six_digit_candidates': codes[:10]})
    except Exception as e:
        ev('inbox_probe_err', {'site': entry.get('site'), 'err': repr(e)[:200]})

# ---------- Safari WebDriver ----------
WD = 'http://127.0.0.1:4444'
def wd(method, path, data=None, timeout=90):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(WD + path, data=body, method=method)
    req.add_header('Content-Type', 'application/json')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            txt = r.read().decode(errors='replace')
            try: return json.loads(txt)
            except Exception: return {'raw': txt}
    except urllib.error.HTTPError as e:
        txt = e.read().decode(errors='replace')
        try: return json.loads(txt)
        except Exception: return {'raw': txt, 'code': e.code}

SID = None
def sess():
    return '/session/%s' % SID
def new_session():
    global SID
    for caps in ({'alwaysMatch': {'browserName': 'safari'}}, {'alwaysMatch': {'browserName': 'safari', 'safari:automaticInspection': False}}):
        r = wd('POST', '/session', {'capabilities': caps}, timeout=120)
        if r.get('value', {}).get('sessionId'):
            SID = r['value']['sessionId']; ev('wd_session', SID); return True
        ev('wd_session_err', r)
    return False
def goto(url):
    return wd('POST', sess() + '/url', {'url': url})
def source():
    r = wd('GET', sess() + '/source'); return r.get('value', '') or ''
def body_text():
    r = wd('GET', sess() + '/element/active')
    r2 = wd('POST', sess() + '/execute/sync', {'script': 'return document.body ? document.body.innerText.slice(0,6000) : "";', 'args': []})
    return r2.get('value', '') or ''
def screenshot(name):
    r = wd('GET', sess() + '/screenshot')
    v = r.get('value')
    if isinstance(v, str) and v:
        open(os.path.join(OUT, name + '.png'), 'wb').write(base64.b64decode(v)); return True
    ev('shot_err', {'name': name, 'r': str(r)[:200]}); return False
def find(css):
    r = wd('POST', sess() + '/element', {'using': 'css selector', 'value': css})
    el = r.get('value', {})
    key = None
    for k in el:
        if k.startswith('element-') or k == 'ELEMENT': key = k
    return el.get(key) if key else None
def find_xp(xp):
    r = wd('POST', sess() + '/element', {'using': 'xpath', 'value': xp})
    el = r.get('value', {}); key = None
    for k in el:
        if k.startswith('element-') or k == 'ELEMENT': key = k
    return el.get(key) if key else None
def click(el):
    return wd('POST', sess() + '/element/%s/click' % el, {})
def keys(el, text):
    return wd('POST', sess() + '/element/%s/value' % el, {'text': text})
def el_text(el):
    return (wd('GET', sess() + '/element/%s/text' % el).get('value') or '')
def js(script, args=None):
    return wd('POST', sess() + '/execute/sync', {'script': script, 'args': args or []}).get('value')
def frame_el():
    return find('#aid-create-widget-iFrame')
def switch_frame(el):
    return wd('POST', sess() + '/frame', {'id': {'element-6066-11e4-a52e-4f735466cecf': el}})

CTL = """return Array.from(document.querySelectorAll('input,select,textarea,button,a[role=button]')).map(function(e){
 return {tag:e.tagName.toLowerCase(),type:(e.type||''),name:(e.name||''),id:(e.id||''),ph:(e.placeholder||''),
 aria:(e.getAttribute('aria-label')||''),auto:(e.getAttribute('autocomplete')||''),text:(e.innerText||'').trim().slice(0,60),
 vis: !!(e.offsetWidth||e.offsetHeight||e.getClientRects().length), disabled:!!e.disabled, value:(e.value||'')};});"""
def controls():
    try: return js(CTL) or []
    except Exception: return []

def dump(page_title, name):
    txt = body_text()
    open(os.path.join(OUT, name + '.txt'), 'w').write(txt)
    open(os.path.join(OUT, name + '.html'), 'w').write(source()[:400000])
    screenshot(name)
    log('===', name, 'title=', page_title, 'len=', len(txt)); log(txt[:1200])
    return txt

def sel_for(c):
    if c.get('id'): return '#' + c['id']
    if c.get('name'): return '%s[name="%s"]' % (c['tag'], c['name'])
    return None

def fill_pat(pat, value, exclude=('hidden', 'submit', 'button', 'checkbox', 'radio', 'file')):
    for c in controls():
        if c['tag'] not in ('input', 'select', 'textarea'): continue
        if c['type'] in exclude or not c['vis'] or c['disabled']: continue
        hay = ' '.join([c['name'], c['id'], c['ph'], c['aria'], c['auto']]).lower()
        if re.search(pat, hay):
            if c['value']: return ('already', c['name'] or c['id'])
            if c['tag'] == 'select':
                if 'month' in hay:
                    opts = js("""var s=document.querySelector(arguments[0]); if(!s) return [];
                      return Array.from(s.options).map(function(o){return [o.value,o.text]});""", ['select' + ('#' + c['id'] if c['id'] else '[name="%s"]' % c['name'])])
                    el = find(sel_for(c))
                    if el:
                        # choose April by index
                        try:
                            wd('POST', sess() + '/element/%s/click' % el, {})
                        except Exception: pass
                        for i in range(1, 13):
                            el2 = find_xp('//select%s/option[%d]' % ("[@id='%s']" % c['id'] if c['id'] else "[@name='%s']" % c['name'], i))
                            if el2:
                                click(el2); return ('selected', i)
                return ('select_unhandled', c['name'] or c['id'])
            el = find(sel_for(c))
            if not el: return ('no_el', c['name'] or c['id'])
            keys(el, value)
            return ('filled', c['name'] or c['id'])
    return ('missing', pat)

def click_text(pat):
    for c in controls():
        if c['tag'] not in ('button', 'a'): continue
        if not c['vis'] or c['disabled']: continue
        if re.search(pat, (c['text'] or ''), re.I):
            el = find(sel_for(c)) if sel_for(c) else None
            if el is None and c['text']:
                el = find_xp('//*[self::button or self::a][contains(normalize-space(.), "%s")]' % c['text'][:30])
            if el:
                click(el); return ('clicked', c['text'])
    return ('missing', pat)

def apple_flow():
    if not new_session(): STATE['stage'] = 'no_session'; save(); return
    ev('window', wd('POST', sess() + '/window/maximize', {}))
    try:
        goto('https://account.apple.com/account#/create')
    except Exception as e:
        ev('goto_err', repr(e)[:200])
    time.sleep(7)
    dump('', '01_landing')
    # dismiss cookie / consent dialogs
    for pat in (r'accept all', r'^accept$', r'^agree$', r'^ok$'):
        r = click_text(pat)
        if r[0] == 'clicked': ev('dismiss', r); time.sleep(2); break
    # find create form: either in iframe or link
    fe = frame_el()
    if not fe:
        r = click_text(r'create (your )?apple account')
        ev('click_create_link', r); time.sleep(7); dump('', '02_after_create_click'); fe = frame_el()
    ev('iframe', bool(fe))
    if fe:
        sw = switch_frame(fe); ev('switch_frame', sw)
        time.sleep(3); dump('', '03_iframe_step')
    ctl = controls(); ev('controls', ctl[:50]); open(os.path.join(OUT, 'controls.json'), 'w').write(json.dumps(ctl, indent=1))
    email = (STATE.get('email') or {}).get('addr') or 'probe@example.com'
    nums = STATE.get('numbers') or []; phone = nums[0]['number'] if nums else ''
    pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14)); STATE['password'] = pw
    for step in range(1, 5):
        STATE['stage'] = 'step_%d' % step; save()
        txt = body_text()
        cap = [k for k in ('enter the characters you see', 'captcha', 'type the characters', 'verify you are human', 'audio challenge') if k in txt.lower()]
        ev('step', {'n': step, 'captcha': cap, 'head': txt[:600]})
        if cap:
            STATE['stage'] = 'captcha_blocked'; STATE['captcha_text'] = txt[:2000]; save(); dump('', '10_captcha'); return
        res = {}
        res['first'] = fill_pat(r'first|given', 'Alex')
        res['last'] = fill_pat(r'last|family|surname', 'Miller')
        res['year'] = fill_pat(r'year|yyyy', '1990')
        res['day'] = fill_pat(r'day|dd', '9')
        res['month'] = fill_pat(r'month', '')
        res['email'] = fill_pat(r'email', email)
        res['phone'] = fill_pat(r'phone|mobile', phone)
        res['password'] = fill_pat(r'password|passcode', pw)
        ev('fill', {'step': step, 'r': {k: str(v) for k, v in res.items()}})
        dump('', '2%d_filled_%d' % (step, step))
        clicked = None
        for pat in (r'continue', r'next', r'create account', r'create your apple account', r'^agree$', r'^create$'):
            r = click_text(pat)
            if r[0] == 'clicked': clicked = r; break
        ev('submit', {'step': step, 'r': clicked})
        if not clicked: break
        time.sleep(8)
        dump('', '3%d_after_%d' % (step, step))
        # iframe may be replaced; re-find frame and controls
        fe2 = frame_el()
        if fe2:
            try: switch_frame(fe2)
            except Exception: pass
        ctl = controls()
        cf = [c for c in ctl if c['tag'] == 'input' and c['vis'] and re.search(r'code|otp|security', (c['name'] + c['id'] + c['aria'] + c['ph']).lower())]
        if cf:
            ev('code_field', cf[:3]); STATE['stage'] = 'code_field_appeared'; save(); dump('', '4%d_code_field' % step); return
    STATE['stage'] = 'flow_end'; save()
    try: wd('DELETE', sess())
    except Exception: pass

def main():
    STATE['stage'] = 'start'; save()
    mailtm_new(); pub_numbers()
    for e in (STATE.get('numbers') or [])[:2]: inbox_probe(e)
    try: apple_flow()
    except Exception:
        ev('flow_exception', traceback.format_exc()[-2000:]); STATE['stage'] = 'flow_exception'
    for e in (STATE.get('numbers') or [])[:2]: inbox_probe(e)
    # fetch any mail once
    try:
        e = STATE.get('email') or {}
        if e.get('token'):
            st, b = http('https://api.mail.tm/messages', headers={'Authorization': 'Bearer ' + e['token']})
            msgs = json.loads(b).get('hydra:member', [])
            STATE['mail_count'] = len(msgs)
            if msgs:
                out = []
                for m in msgs[:3]:
                    st2, b2 = http('https://api.mail.tm/messages/' + m['id'], headers={'Authorization': 'Bearer ' + e['token']})
                    out.append(json.loads(b2))
                open(os.path.join(OUT, 'emails.json'), 'w').write(json.dumps(out, indent=1, ensure_ascii=False)[:20000])
    except Exception as ex: ev('mail_fetch_err', repr(ex)[:200])
    save(); log('DONE stage=', STATE['stage'])

if __name__ == '__main__':
    try: main()
    except Exception:
        ev('fatal', traceback.format_exc()[-2000:]); save(); raise
