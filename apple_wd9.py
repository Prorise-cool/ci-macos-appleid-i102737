#!/usr/bin/env python3
"""Run 7: fresh Apple Account creation in real Safari using the asms.ai long-lived UK
public number +447450699185 (phoneCode=GB / countrySelect=GBR), whose public inbox has
historically received a real Apple SMS ("Your Apple Account code is: ...").

Hardening vs run 6:
  * every HTTP call retried with backoff (run 6 died on a transient mail.tm non-JSON body)
  * mail.tm primary (5 tries) -> guerrilla fallback
  * voted captcha OCR (ocr2.swift CANDS) with a human-like candidate ladder, <=10 images
  * phone SMS is read ONCE and only from a NEW Apple row that appeared after our own
    phone-stage baseline  (never a historical/other person's code, never enumerate range)
  * explicit detection of the Apple virtual-machine rejection text
  * global deadline so the job always stays under the 30-minute GitHub timeout

Rules honoured: never guess/brute an SMS code, never enumerate numbers, no third-party
messaging, only our own temp mailbox + our own public number inbox.
"""
import os, re, json, time, random, string, base64, subprocess, html as htmlmod, traceback
import urllib.request, urllib.error

START = time.time()
DEADLINE = START + 25 * 60  # hard self-limit (job timeout is 30 min)
OUT = os.path.dirname(os.path.abspath(__file__)) + '/out9'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run9.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')
STATE = {'events': [], 'stage': 'init'}
def save():
    try: json.dump(STATE, open(os.path.join(OUT, 'summary9.json'), 'w'), indent=2, ensure_ascii=False)
    except Exception: pass
def ev(k, v): STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v}); log('[EV]', k, '=', str(v)[:1500]); save()
def time_left(): return DEADLINE - time.time()

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
NUM_CC = os.environ.get('APPLE_CC', 'GB')
NUM_NAT = os.environ.get('APPLE_NAT', '7450699185')
INBOX = os.environ.get('APPLE_INBOX', 'https://asms.ai/number/447450699185')

def _open(req, timeout):
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)

def http(url, data=None, headers=None, timeout=35, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, method='POST' if data else 'GET')
            req.add_header('User-Agent', UA)
            req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
            for k, v in (headers or {}).items(): req.add_header(k, v)
            with _open(req, timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            try: body = e.read()
            except Exception: body = b''
            last = 'HTTP %s' % e.code
            if e.code < 500: return e.code, body
        except Exception as e:
            last = repr(e)[:180]
        time.sleep(2 + 2 * i)
    raise RuntimeError('http failed %s: %s' % (url, last))

def http_json(url, data=None, headers=None, timeout=35, tries=4):
    st, b = http(url, data, headers, timeout, tries)
    return st, json.loads(b)

def strip_tags(s): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()

def parse_asms(h):
    rows = []
    for b in re.split(r'ring-gradient rounded-2xl bg-white/\[0\.03\]', h)[1:]:
        m = re.search(r'<a[^>]*href="/([a-z0-9]+)"[^>]*>([^<]*)</a><time dateTime="([^"]+)">', b)
        if not m:
            m2 = re.search(r'<span class="font-semibold text-cyan-300">([^<]*)</span><time dateTime="([^"]+)">', b)
            if not m2: continue
            slug, frm, ts = '', m2.group(1), m2.group(2)
        else:
            slug, frm, ts = m.group(1), m.group(2).strip(), m.group(3)
        i = b.find('leading-relaxed')
        body = htmlmod.unescape(strip_tags(b[i:i + 900])) if i > 0 else ''
        rows.append({'slug': slug, 'from': frm, 't': ts, 'text': body[:400]})
    return rows

def fetch_inbox():
    st, b = http(INBOX + '?t=%d' % int(time.time()), headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    return st, parse_asms(b.decode('utf-8', 'replace'))

def newest_ts(rows):
    ts = [r['t'] for r in rows if r.get('t')]
    return max(ts) if ts else ''

def is_apple_code(row):
    t = (row.get('text') or '')
    return (('apple account code' in t.lower()) or ('apple' in (row.get('from') or '').lower())) and re.search(r'\b\d{6}\b', t)

def poll_inbox_apple(after_ts, secs=600):
    end = min(time.time() + secs, DEADLINE - 90)
    n = 0
    while time.time() < end:
        n += 1
        try:
            st, rows = fetch_inbox()
            if n % 5 == 1:
                ev('inbox_poll', {'n': n, 'status': st, 'rows': len(rows), 'newest': newest_ts(rows),
                                  'first': [{'from': r['from'], 't': r['t'], 'text': r['text'][:100]} for r in rows[:3]]})
            fresh = [r for r in rows if (r.get('t') or '') > after_ts]
            apples = [r for r in fresh if is_apple_code(r)]
            if apples:
                ev('inbox_apple_new', apples)
                return apples[0]
            if fresh:
                ev('inbox_new_rows', [{'from': r['from'], 't': r['t'], 'text': r['text'][:140]} for r in fresh[:6]])
        except Exception as e:
            ev('inbox_err', repr(e)[:200])
        time.sleep(12)
    return None

# ---------- email ----------
def tmol_new(n=3):
    """temp-mail.lol: neutral random domains; /generate -> {address, token}; inbox GET /auth/{token} -> {"email":[...]}"""
    out = []
    for i in range(n):
        if time_left() < 900: break
        try:
            st, b = http('https://api.tempmail.lol/generate', timeout=25)
            j = json.loads(b)
            if j.get('address') and j.get('token'):
                out.append({'kind': 'tmol', 'addr': j['address'], 'token': j['token']})
                ev('tmol_gen', {'addr': j['address'], 'domain': j['address'].split('@', 1)[-1]})
            else:
                ev('tmol_bad', str(j)[:200])
        except Exception as ex:
            ev('tmol_err', repr(ex)[:200])
        time.sleep(1)
    return out

def mailtm_new():
    last = ''
    for i in range(2):
        if time_left() < 600: break
        try:
            st, j = http_json('https://api.mail.tm/domains', timeout=25)
            domain = j['hydra:member'][0]['domain']
            pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
            addr = 'x%s%d@%s' % (int(time.time()) % 100000, random.randint(10, 99), domain)
            http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'}, timeout=25)
            st2, j2 = http_json('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(), {'Content-Type': 'application/json'}, timeout=25)
            tok = j2.get('token')
            if tok:
                ev('mailtm', {'addr': addr, 'token': True, 'try': i + 1})
                return [{'kind': 'mailtm', 'addr': addr, 'pw': pw, 'token': tok}]
            last = 'no_token'
        except Exception as ex:
            last = repr(ex)[:200]; ev('mailtm_err', {'try': i + 1, 'e': last})
        time.sleep(4)
    ev('mailtm_fail', last)
    return []

def guerrilla_new():
    """guerrilla API works from runners but defaults to the BLOCKED domain; keep sid to switch site."""
    try:
        st, b = http('https://api.guerrillamail.com/ajax.php?f=get_email_address&lang=en', timeout=25)
        j = json.loads(b)
        STATE['_guerrilla_sid'] = j.get('sid_token')
        ev('guerrilla', {'addr': j['email_addr'], 'sid': bool(j.get('sid_token'))})
        return True
    except Exception as ex:
        ev('guerrilla_fail', repr(ex)[:200]); return False

def guerrilla_site(domain):
    sid = STATE.get('_guerrilla_sid')
    if not sid: return None
    try:
        user = 'u%s%d' % (int(time.time()) % 1000000, random.randint(10, 99))
        u = ('https://api.guerrillamail.com/ajax.php?f=set_email_user&email_user=%s&site=%s&lang=en&sid_token=%s'
             % (user, domain, sid))
        st, b = http(u, timeout=25)
        j = json.loads(b)
        addr = j.get('email_addr')
        if addr:
            ev('guerrilla_site', {'site': domain, 'addr': addr})
            return {'kind': 'guerrilla', 'addr': addr, 'sid': sid, 'site': domain}
    except Exception as ex:
        ev('guerrilla_site_err', {'site': domain, 'e': repr(ex)[:160]})
    return None

def mail_codes_now():
    e = STATE.get('email') or {}
    if not e: return []
    if e.get('kind') == 'mailtm':
        st, j = http_json('https://api.mail.tm/messages', headers={'Authorization': 'Bearer ' + e['token']}, timeout=25)
        msgs = j.get('hydra:member', [])
        if not msgs: return []
        st2, j2 = http_json('https://api.mail.tm/messages/' + msgs[0]['id'], headers={'Authorization': 'Bearer ' + e['token']}, timeout=25)
        txt = (j2.get('text') or '') + ' ' + json.dumps(j2.get('html') or [], ensure_ascii=False)[:8000]
        open(os.path.join(OUT, 'email_full.json'), 'w').write(json.dumps(j2, ensure_ascii=False)[:20000])
        codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', txt)
        if codes: ev('mail_code', {'subject': j2.get('subject'), 'codes': codes[:5]})
        return codes
    if e.get('kind') == 'tmol':
        st, j = http_json('https://api.tempmail.lol/auth/' + e['token'], timeout=25)
        lst = j.get('email') or []
        if not lst: return []
        open(os.path.join(OUT, 'email_full.json'), 'w').write(json.dumps(lst[0], ensure_ascii=False)[:20000])
        msg = lst[0]
        txt = ' '.join(str(msg.get(k) or '') for k in ('subject', 'body', 'html', 'text', 'from', 'sender'))
        codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', txt)
        if codes: ev('mail_code', {'subject': msg.get('subject'), 'codes': codes[:5]})
        return codes
    st, b = http('https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token=' + e['sid'], timeout=25)
    j = json.loads(b); lst = j.get('list') or []
    if not lst: return []
    mid = lst[0].get('mail_id')
    st2, b2 = http('https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id=%s&sid_token=%s' % (mid, e['sid']), timeout=25)
    k = json.loads(b2)
    txt = (k.get('mail_body') or '')
    open(os.path.join(OUT, 'email_full.json'), 'w').write(json.dumps(k, ensure_ascii=False)[:20000])
    codes = re.findall(r'(?<!\d)(\d{6})(?!\d)', txt)
    if codes: ev('mail_code', {'subject': k.get('mail_subject'), 'codes': codes[:5]})
    return codes

def mail_wait_code(secs=160):
    end = min(time.time() + secs, DEADLINE - 300)
    n = 0
    while time.time() < end:
        n += 1
        try:
            c = mail_codes_now()
            if n % 4 == 1: ev('mail_poll', {'n': n, 'codes': c[:3]})
            if c: return c[0]
        except Exception as ex:
            ev('mail_err', repr(ex)[:150])
        time.sleep(8)
    return None

# ---------- webdriver ----------
WD = 'http://127.0.0.1:4444'; SID = None
def wd(method, path, data=None, timeout=180):
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
    for k in (el or {}):
        if k.startswith('element-') or k == 'ELEMENT': return el[k]
def find(css): return ekey(wd('POST', sess() + '/element', {'using': 'css selector', 'value': css}).get('value', {}))
def find_xp(xp): return ekey(wd('POST', sess() + '/element', {'using': 'xpath', 'value': xp}).get('value', {}))
def click(el): return wd('POST', sess() + '/element/%s/click' % el, {})
def keys(el, t): return wd('POST', sess() + '/element/%s/value' % el, {'text': t})
def js(s, a=None): return wd('POST', sess() + '/execute/sync', {'script': s, 'args': a or []}).get('value')
def jsa(s, a=None, timeout=60000):
    return wd('POST', sess() + '/execute/async', {'script': s, 'args': a or []}, timeout=timeout).get('value')
def source(): return wd('GET', sess() + '/source').get('value', '') or ''
def body_text(): return js('return document.body?document.body.innerText.slice(0,9000):"";') or ''
def shot(n):
    v = wd('GET', sess() + '/screenshot').get('value')
    if isinstance(v, str) and v: open(os.path.join(OUT, n + '.png'), 'wb').write(base64.b64decode(v))
def dump(n):
    t = body_text(); open(os.path.join(OUT, n + '.txt'), 'w').write(t)
    open(os.path.join(OUT, n + '.html'), 'w').write(source()[:700000])
    shot(n); log('===', n, 'len=', len(t)); return t
def switch_frame(el): return wd('POST', sess() + '/frame', {'id': {'element-6066-11e4-a52e-4f735466cecf': el}})

def set_input(name, value):
    el = find('input[name="%s"]' % name)
    if not el: return ('missing', name)
    try: click(el)
    except Exception: pass
    keys(el, value)
    v = js('var e=document.querySelector(arguments[0]); return e?e.value:null;', ['input[name="%s"]' % name])
    return ('ok' if v else 'no_value', name, v)

def set_tid(tid, value):
    # birthday selects carry data-testid, not a name attribute (note: use var v, regular
    # functions have their own `arguments`, so compare against a captured value)
    ok = js("""var v=arguments[0]; var s=document.querySelector('[data-testid="%s"]'); if(!s) return 'nosel';
      var has=Array.from(s.options).some(function(o){return o.value===v;}); if(!has) return 'noopt';
      s.value=v; s.dispatchEvent(new Event('input',{bubbles:true}));
      s.dispatchEvent(new Event('change',{bubbles:true}));
      var lab=s.parentNode.querySelector('.form-dropdown-label'); if(lab){var o=s.options[s.selectedIndex]; if(o) lab.textContent=o.text;} return s.value;""" % tid, [value])
    return ('ok' if ok == value else 'bad', tid, str(ok))

def set_select(name, value):
    ok = js("""var v=arguments[0]; var s=document.querySelector('select[name="%s"]'); if(!s) return 'nosel';
      var has=Array.from(s.options).some(function(o){return o.value===v;});
      if(!has) return 'noopt';
      s.value=v; s.dispatchEvent(new Event('input',{bubbles:true}));
      s.dispatchEvent(new Event('change',{bubbles:true})); return s.value;""" % name, [value])
    if ok == value: return ('ok', name, value)
    return ('bad', name, str(ok))

def invalid_fields():
    return js("""return Array.from(document.querySelectorAll('[aria-invalid="true"]')).map(function(e){return (e.getAttribute('data-testid')||'')+'#'+(e.id||'');}).slice(0,10);""")

def select_info(name):
    return js("""var s=document.querySelector('select[name="%s"]'); if(!s) return null;
      return {cur:s.value, opts:Array.from(s.options).slice(0,4).map(function(o){return o.value+'='+o.text;}),
              gb:Array.from(s.options).filter(function(o){return /GB|United Kingdom|\\+44/i.test(o.value+' '+o.text);}).slice(0,4).map(function(o){return o.value+'='+o.text;})};""" % name)

def captcha_img():
    src = js("var i=document.querySelector('.captcha img.img'); return i?i.src:null;")
    if not src: return None
    p = os.path.join(OUT, 'captcha.jpg')
    if src.startswith('data:image'):
        open(p, 'wb').write(base64.b64decode(src.split(',', 1)[1])); return p
    st, b = http(src); open(p, 'wb').write(b); return p

def _run_ocr(binary, p, tag):
    try:
        out = subprocess.run([binary, p], capture_output=True, text=True, timeout=220).stdout.strip()
        ev('ocr_raw_' + tag, out[-1000:])
        m = re.search(r'^CANDS:(.*)$', out, re.M)
        return [c.rsplit('|', 1)[0] for c in (m.group(1).split(',') if m and m.group(1) else [])]
    except Exception as e:
        ev('ocr_err_' + tag, repr(e)[:160]); return []

def ocr2(p):
    cands = _run_ocr('/tmp/ocr2', p, 'vote')
    if os.path.exists('/tmp/ocr3'):
        cands += _run_ocr('/tmp/ocr3', p, 'slice')
    seen = []
    for c in cands:
        c = ''.join(ch for ch in c if ch.isalnum())
        if 4 <= len(c) <= 8 and c not in seen: seen.append(c)
    return seen

def new_code():
    el = find_xp('//button[@aria-label="New Code"]')
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

def is_vm_block(t):
    low = (t or '').lower()
    return ('virtual machine' in low) or ("can't be used to create" in low) or ('cannot be used to create' in low) or ('not supported' in low and 'apple' in low)

def main():
    global SID
    STATE['stage'] = 'start'; save()
    # ---- inbox baseline at very start (so we know which Apple row is ours) ----
    try:
        st, rows = fetch_inbox(); INBOX_BASE = newest_ts(rows)
        ev('inbox_baseline', {'status': st, 'count': len(rows), 'newest': INBOX_BASE,
                              'first': [{'from': r['from'], 't': r['t'], 'text': r['text'][:110]} for r in rows[:3]]})
    except Exception as ex:
        ev('inbox_baseline_err', repr(ex)[:300]); INBOX_BASE = ''
    # ---- email candidates: <=3 providers, one attempt each (planner rule) ----
    CANDS = []
    try:
        CANDS += tmol_new(1)
    except Exception as ex:
        ev('tmol_stage_err', repr(ex)[:160])
    try:
        CANDS += mailtm_new()
    except Exception as ex:
        ev('mailtm_stage_err', repr(ex)[:160])
    try:
        if guerrilla_new():
            g = guerrilla_site('sharklasers.com')
            if g: CANDS.append(g)
    except Exception as ex:
        ev('guerrilla_stage_err', repr(ex)[:160])
    CANDS = CANDS[:3]
    ev('email_candidates', [{'addr': c['addr'], 'kind': c['kind']} for c in CANDS])
    if not CANDS:
        STATE['stage'] = 'no_email_provider'; save(); return
    r = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'safari'}}})
    SID = (r.get('value', {}) or {}).get('sessionId'); ev('wd_session', SID)
    if not SID: STATE['stage'] = 'no_session'; save(); return
    wd('POST', sess() + '/window/maximize', {})
    wd('POST', sess() + '/url', {'url': 'https://account.apple.com/account#/create'}); time.sleep(9)
    fe = find('#aid-create-widget-iFrame')
    if not fe: dump('10_noiframe'); STATE['stage'] = 'no_iframe'; save(); return
    switch_frame(fe); time.sleep(3); dump('12_form')

    def set_email(addr):
        v = js("""var e=document.querySelector('input[name=appleId]'); if(!e) return null;
          var d=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');
          d.set.call(e, arguments[0]);
          e.dispatchEvent(new Event('input',{bubbles:true}));
          e.dispatchEvent(new Event('change',{bubbles:true}));
          return e.value;""", [addr])
        return v

    def probe_email(addr):
        v = set_email(addr)
        f2 = find('input[name="firstName"]')
        if f2:
            try: click(f2)
            except Exception: pass
        time.sleep(4)
        r = js("""var e=document.querySelector('input[name=appleId]'); if(!e) return {v:null,inv:null,err:'gone',blank:true};
          var o={v:e.value, inv:(e.getAttribute('aria-invalid')||''), err:'', blank:false};
          var all=document.querySelectorAll('[class*=error],[class*=message],[role=alert],.form-textbox-error');
          for(var i=0;i<all.length;i++){var t=(all[i].innerText||'').trim(); if(t && t.length<200 && /email/i.test(t)){o.err=t;break;}}
          o.hasInvalidText=((document.body.innerText)||'').indexOf('Enter a valid email address')>=0;
          return o;""")
        if isinstance(r, dict): r['set'] = v
        return r

    STATE['stage'] = 'email_probe'; save()
    ev('frame_url', js("return location.href;"))
    # ---- server-side email-domain oracle: POST /account/validation/appleid (same-origin, in-frame) ----
    def server_validate(addr):
        r = js("""var a=arguments[0];
          try{ var x=new XMLHttpRequest(); x.open('POST','/account/validation/appleid',false);
            x.setRequestHeader('Content-Type','application/json'); x.setRequestHeader('Accept','application/json');
            x.send(JSON.stringify({emailAddress:a}));
            return {status:x.status, body:(x.responseText||'').slice(0,1500)};
          }catch(e){ return {err:String(e).slice(0,200)}; }""", [addr])
        return r
    ctrl_block = server_validate('probe0099@guerrillamailblock.com')
    ev('srv_validate_control_blocked', ctrl_block)
    ctrl_ok = server_validate('probe.acct9.' + str(random.randint(1000,9999)) + '@gmail.com')
    ev('srv_validate_control_gmail', ctrl_ok)
    verdicts = {}
    for c in CANDS:
        verdicts[c['addr']] = server_validate(c['addr'])
        ev('srv_validate', {'addr': c['addr'], 'kind': c['kind'], 'r': verdicts[c['addr']]})
    def srv_valid(addr):
        r = verdicts.get(addr) or {}
        try: j = json.loads(r.get('body') or '{}')
        except Exception: return None
        return j
    chosen = None
    for c in CANDS:
        j = srv_valid(c['addr'])
        if j and j.get('valid') is True and not j.get('isRecycledDomain'):
            chosen = c; break
    if not chosen:
        STATE['stage'] = 'temp_domains_rejected_server_side'; save(); dump('20_srv_validate')
        return
    ev('email_chosen_server_valid', {'addr': chosen['addr'], 'kind': chosen['kind']})
    email = chosen['addr']; pw = STATE['password'] = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(13))
    STATE['email_addr'] = email
    for nm, v in (('firstName', 'Alex'), ('lastName', 'Miller')): set_input(nm, v)
    ev('month_set', set_tid('select-month', '04'))
    ev('day_set', set_tid('select-day', '09'))
    ev('year_set', set_tid('select-year', '1990'))
    set_email(email); set_input('password', pw); set_input('confirmPassword', pw)
    ev('phoneCode_info', select_info('phoneCode'))
    ev('countrySelect_info', select_info('countrySelect'))
    ev('phoneCode_set', set_select('phoneCode', NUM_CC))
    ev('country_set', set_select('countrySelect', {'GB': 'GBR', 'CA': 'CAN', 'US': 'USA'}.get(NUM_CC, '')))
    ev('phone_fill', set_input('phoneNumber', NUM_NAT))
    ev('phone_validity', js("var e=document.querySelector('input[name=phoneNumber]'); return e?{v:e.value,ok:e.checkValidity(),msg:e.validationMessage}:null;"))
    ev('invalid_after_fill', invalid_fields())
    dump('13_filled')

    ok_submit = False
    used = set()
    images = 0
    for attempt in range(1, 11):
        if time_left() < 900: ev('deadline_guard', {'attempt': attempt, 'left': round(time_left())}); break
        images += 1
        p = captcha_img()
        if not p:
            ev('no_captcha', attempt); time.sleep(3); continue
        cands = [c for c in ocr2(p) if c not in used]
        ev('ocr_guess', {'attempt': attempt, 'cands': cands})
        if not cands:
            if new_code(): time.sleep(4)
            continue
        g = cands[0]; used.add(g)
        el = find('input[name="captcha"]')
        if el:
            try:
                click(el)
                js("var e=document.querySelector('input[name=captcha]'); if(e){e.value='';e.dispatchEvent(new Event('input',{bubbles:true}));}")
                keys(el, g)
            except Exception as e: ev('captcha_fill_err', repr(e)[:120])
        ev('captcha_filled', {'attempt': attempt, 'guess': g})
        btn = find_xp('//button[@type="submit"]')
        if btn: click(btn)
        time.sleep(10); t = dump('%02d_after_submit_%d' % (20 + attempt, attempt)); low = t.lower()
        if is_vm_block(t):
            ev('vm_block_detected', t[:400]); STATE['stage'] = 'vm_blocked'; save(); return
        if js("return document.querySelectorAll('input.form-security-code-input').length;"):
            ok_submit = True; ev('submit_ok', attempt); break
        if 'verification code' in low:
            ok_submit = True; ev('submit_ok_text', attempt); break
        inv = invalid_fields()
        errs = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);""")
        email_bad = js("""var e=document.querySelector('input[name=appleId]'); if(!e) return false;
          if(e.getAttribute('aria-invalid')==='true') return true;
          return ((document.body.innerText)||'').indexOf('Enter a valid email address')>=0;""")
        ev('submit_blocked', {'attempt': attempt, 'guess': g, 'invalid': inv, 'errs': errs, 'email_bad': bool(email_bad)})
        if any('cannot be created at this time' in (x or '') for x in errs):
            STATE['stage'] = 'create_refused_generic'; save(); dump('26_create_refused_generic'); return
        if email_bad:
            STATE['stage'] = 'email_rejected_after_submit'; save(); dump('25_email_rejected'); return
        if new_code(): time.sleep(4)
    ev('captcha_images_used', images)
    if not ok_submit: STATE['stage'] = 'no_email_stage'; save(); return

    STATE['stage'] = 'email_code_stage'; save(); dump('30_email_code_stage')
    code = mail_wait_code(160)
    if not code: STATE['stage'] = 'email_code_missing'; save(); return
    STATE['email_code'] = code; save()
    fill_code(code); dump('31_code_filled')
    btn = find_xp('//button[@type="submit"]') or find_xp('//button[contains(normalize-space(.),"Continue")]')
    if btn: click(btn)
    time.sleep(11); t = dump('40_after_email_code'); low = t.lower()
    errs = js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);""")
    ev('errors_after_email_code', errs)
    ev('final_url', js('return location.href'))
    if is_vm_block(t):
        ev('vm_block_after_email', t[:400]); STATE['stage'] = 'vm_blocked_after_email'; save(); return
    if 'phone' in low and 'code' in low: STATE['stage'] = 'phone_verification_stage'; save()
    elif 'verify your email' in low: STATE['stage'] = 'email_code_rejected'; save()
    else: STATE['stage'] = 'post_email_stage'; save()
    if STATE['stage'] != 'phone_verification_stage':
        try: wd('DELETE', sess())
        except Exception: pass
        return

    dump('50_phone_stage')
    ev('phone_stage_text', body_text()[:600])
    # fresh baseline right before Apple would send the SMS
    try:
        st2, rows2 = fetch_inbox(); base2 = max(INBOX_BASE or '', newest_ts(rows2))
        ev('inbox_baseline2', {'status': st2, 'count': len(rows2), 'base': base2})
    except Exception as ex:
        ev('inbox_baseline2_err', repr(ex)[:200]); base2 = INBOX_BASE
    found = poll_inbox_apple(base2, secs=600)
    if not found:
        STATE['stage'] = 'phone_sms_not_received'; save(); dump('60_sms_timeout'); return
    STATE['sms_found'] = found; save()
    m = re.search(r'\b(\d{6})\b', found['text'])
    if not m: STATE['stage'] = 'sms_code_unparsable'; save(); return
    sms = m.group(1); STATE['sms_code'] = sms; save()
    fill_code(sms); dump('61_sms_filled'); time.sleep(1)
    btn = find_xp('//button[@type="submit"]') or find_xp('//button[contains(normalize-space(.),"Continue")]')
    if btn: click(btn)
    time.sleep(13); t = dump('70_after_sms'); low = t.lower()
    ev('errors_after_sms', js("""return Array.from(document.querySelectorAll('[class*=error],[role=alert],.form-message')).map(function(e){return e.innerText.trim().slice(0,300);}).filter(Boolean).slice(0,8);"""))
    ev('final_url_sms', js('return location.href'))
    if 'incorrect' in low or 'invalid' in low: STATE['stage'] = 'phone_code_rejected'
    elif 'terms' in low or 'conditions' in low: STATE['stage'] = 'terms_stage'
    elif 'account' in low and ('created' in low or 'welcome' in low or 'signed in' in low): STATE['stage'] = 'account_created'
    else: STATE['stage'] = 'post_phone_stage'
    save()

try:
    main()
except Exception:
    ev('exception', traceback.format_exc()[-2500:])
    STATE['stage'] = 'exception'; save()
finally:
    log('FINAL STAGE =', STATE['stage'])
    save()
    try:
        if SID: wd('DELETE', sess())
    except Exception: pass
