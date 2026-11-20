#!/usr/bin/env python3
"""Headful (real GUI) attempt to create an Apple Account inside a macOS GitHub runner.
Every stage writes evidence into out/. No guessing of any verification code."""
import os, re, json, time, random, string, sys, traceback, subprocess
import urllib.request, urllib.error

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'run.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s); LOG.write(s + '\n')

STATE = {'stage': 'init', 'events': []}
def ev(k, v):
    STATE['events'].append({'t': round(time.time(), 2), 'k': k, 'v': v})
    log('[EV]', k, '=', str(v)[:800])

def save_json():
    with open(os.path.join(OUT, 'summary.json'), 'w') as f:
        json.dump(STATE, f, indent=2, ensure_ascii=False)

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
def http(url, data=None, headers=None, timeout=30, method=None):
    req = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'))
    req.add_header('User-Agent', UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=timeout) as r:
        return r.status, r.read()

# ---------------- stage: temp email (mail.tm) ----------------
def mailtm_new():
    try:
        st, b = http('https://api.mail.tm/domains')
        doms = json.loads(b.decode())['hydra:member']
        domain = doms[0]['domain']
        pw = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
        addr = 'a%s%s@%s' % (int(time.time()) % 100000, random.randint(100, 999), domain)
        st, b = http('https://api.mail.tm/accounts', json.dumps({'address': addr, 'password': pw}).encode(),
                     {'Content-Type': 'application/json'})
        ev('mailtm_account', {'status': st, 'addr': addr, 'body': b.decode()[:300]})
        st, b = http('https://api.mail.tm/token', json.dumps({'address': addr, 'password': pw}).encode(),
                     {'Content-Type': 'application/json'})
        tok = json.loads(b.decode()).get('token')
        STATE['email'] = {'addr': addr, 'pw': pw, 'token': tok, 'domain': domain}
        save_json()
        return True
    except Exception as e:
        ev('mailtm_error', repr(e))
        return False

def mailtm_fetch(q=''):
    e = STATE.get('email') or {}
    if not e.get('token'):
        return []
    try:
        st, b = http('https://api.mail.tm/messages', headers={'Authorization': 'Bearer ' + e['token']})
        msgs = json.loads(b.decode()).get('hydra:member', [])
        out = []
        for m in msgs[:5]:
            st2, b2 = http('https://api.mail.tm/messages/' + m['id'], headers={'Authorization': 'Bearer ' + e['token']})
            out.append(json.loads(b2.decode()))
        return out
    except Exception as ex:
        ev('mailtm_fetch_err', repr(ex))
        return []

# ---------------- stage: public receive-sms numbers ----------------
SMS_SITES = [
    ('receive-smss', 'https://receive-smss.com/'),
    ('smsreceivefree', 'https://smsreceivefree.com/'),
    ('receivesms.co', 'https://receivesms.co/'),
    ('anonymsms', 'https://anonymsms.com/'),
    ('sms-online', 'https://sms-online.co/'),
    ('quackr', 'https://quackr.io/'),
]
def pub_numbers():
    found = []
    for name, url in SMS_SITES:
        try:
            st, b = http(url, timeout=25)
            html = b.decode(errors='ignore')
            with open(os.path.join(OUT, 'sms_%s.html' % name), 'wb') as f:
                f.write(b)
            cands = []
            for m in re.finditer(r'(?:\+1[\s\-\.]?)?\(?([2-9]\d{2})\)?[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})', html):
                n = '+1' + m.group(1) + m.group(2) + m.group(3)
                if n not in cands:
                    cands.append(n)
            ev('sms_site', {'name': name, 'status': st, 'bytes': len(html), 'n': len(cands), 'first': cands[:3]})
            if cands:
                found.append({'site': name, 'url': url, 'number': cands[0], 'all_first': cands[:5]})
        except Exception as e:
            ev('sms_site_err', {'name': name, 'err': repr(e)[:200]})
    STATE['numbers'] = found
    save_json()
    return found

def inbox_probe(entry):
    """Single read of the public inbox page for the chosen number; never guesses anything."""
    try:
        url = entry['url']
        st, b = http(url, timeout=25)
        html = b.decode(errors='ignore')
        fn = os.path.join(OUT, 'inbox_%s.html' % entry['site'].replace('.', '_'))
        open(fn, 'wb').write(b)
        digits = entry['number'].replace('+1', '')
        near = []
        for m in re.finditer(re.escape(digits) + r'.{0,600}', html, re.S):
            near.append(re.sub(r'<[^>]+>', ' ', m.group(0))[:400])
        codes = sorted(set(re.findall(r'\b\d{6}\b', html)))
        has_apple = ('apple' in html.lower())
        res = {'site': entry['site'], 'status': st, 'bytes': len(html), 'apple_word': has_apple,
               'six_digit_candidates': codes[:10], 'near': near[:2]}
        ev('inbox_probe', res)
        return res
    except Exception as e:
        ev('inbox_probe_err', {'site': entry.get('site'), 'err': repr(e)[:200]})
        return {'error': repr(e)}

# ---------------- stage: headful browser ----------------
def dump(page, name):
    try:
        page.screenshot(path=os.path.join(OUT, name + '.png'), full_page=True)
    except Exception as e:
        ev('shot_err', {'name': name, 'err': repr(e)[:120]})
    try:
        open(os.path.join(OUT, name + '.html'), 'w').write(page.content())
    except Exception:
        pass
    info = {'url': page.url, 'title': '', 'text': ''}
    try:
        info['title'] = page.title()
    except Exception:
        pass
    try:
        info['text'] = page.inner_text('body')[:4000]
    except Exception:
        pass
    open(os.path.join(OUT, name + '.txt'), 'w').write(json.dumps(info, indent=2, ensure_ascii=False))
    log('===', name, 'url=', info['url'], 'title=', info['title'])
    log(info['text'][:1500])
    return info

CTL_JS = """() => Array.from(document.querySelectorAll('input,select,textarea,button,[role=button],a')).map(e=>({
 tag:e.tagName.toLowerCase(), type:(e.type||''), name:(e.name||''), id:(e.id||''),
 ph:(e.placeholder||''), aria:(e.getAttribute('aria-label')||''), auto:(e.getAttribute('autocomplete')||''),
 cls:(e.className||'').toString().slice(0,80), text:(e.innerText||'').trim().slice(0,80),
 vis: !!(e.offsetWidth||e.offsetHeight||e.getClientRects().length), disabled:!!e.disabled, value:(e.value||'')}))"""

def frame_controls(frame):
    try:
        return frame.evaluate(CTL_JS)
    except Exception as e:
        return []

def best(frame):
    """pick the frame that actually holds the form"""
    cands = []
    for f in frame:
        ctl = frame_controls(f)
        n_input = sum(1 for c in ctl if c['tag'] in ('input', 'select'))
        if n_input:
            cands.append((n_input, f, ctl))
    cands.sort(key=lambda x: -x[0])
    return cands[0] if cands else (0, None, [])

def fill_by(frame, ctl, pat, value, exclude_types=('hidden', 'submit', 'button', 'checkbox', 'radio')):
    for c in ctl:
        if c['tag'] not in ('input', 'select', 'textarea'):
            continue
        if c['type'] in exclude_types or not c['vis'] or c['disabled']:
            continue
        hay = ' '.join([c['name'], c['id'], c['ph'], c['aria'], c['auto']]).lower()
        if re.search(pat, hay):
            if c['value']:
                return ('already', c['name'] or c['id'])
            sel = ('#' + c['id']) if c['id'] else ('[name="%s"]' % c['name'])
            try:
                if c['tag'] == 'select':
                    frame.locator(sel).first.select_option(index=random.randint(1, 12), timeout=4000)
                else:
                    frame.locator(sel).first.fill(value, timeout=5000)
                return ('filled', c['name'] or c['id'])
            except Exception as e:
                return ('err', (c['name'] or c['id'], repr(e)[:120]))
    return ('missing', pat)

def click_by(frame, ctl, pat):
    for c in ctl:
        if c['tag'] not in ('button', 'a', 'input'):
            continue
        if not c['vis'] or c['disabled']:
            continue
        txt = (c['text'] + ' ' + c['value'] + ' ' + c['aria']).strip()
        if re.search(pat, txt, re.I):
            sel = ('#' + c['id']) if c['id'] else None
            try:
                if sel:
                    frame.locator(sel).first.click(timeout=5000)
                else:
                    frame.get_by_text(re.compile(pat, re.I)).first.click(timeout=5000)
                return ('clicked', txt)
            except Exception as e:
                return ('err', repr(e)[:120])
    return ('missing', pat)

def captcha_present(text):
    t = text.lower()
    keys = ['enter the characters you see', 'captcha', 'type the characters', 'audio challenge', 'verify you are human']
    return [k for k in keys if k in t]

def browser_attempt():
    from playwright.sync_api import sync_playwright
    prof = os.path.join(OUT, 'chromeprofile')
    with sync_playwright() as p:
        ctx = None; errors = []
        for ch in ('chrome', 'msedge'):
            try:
                ctx = p.chromium.launch_persistent_context(
                    prof, channel=ch, headless=False,
                    args=['--no-first-run', '--no-default-browser-check', '--disable-blink-features=AutomationControlled'],
                    viewport={'width': 1440, 'height': 1000}, locale='en-US', timezone_id='America/Los_Angeles')
                ev('browser_launched', ch)
                break
            except Exception as e:
                errors.append((ch, repr(e)[:200]))
                ev('browser_launch_err', errors[-1])
        if ctx is None:
            STATE['stage'] = 'browser_launch_failed'; save_json(); return False
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30000)
        # 1) landing
        try:
            page.goto('https://account.apple.com/account#/create', wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            ev('goto_err', repr(e)[:200])
        time.sleep(6)
        dump(page, '01_account_create')
        # 2) find form (page or iframe)
        frame = None
        for _ in range(3):
            n, f, ctl = best(page.frames)
            if f is not None:
                frame = f; break
            time.sleep(4)
        ev('form_frame', {'n_inputs': n if frame else 0, 'url': frame.url if frame else None})
        if frame is None:
            dump(page, '02_no_form'); STATE['stage'] = 'no_form'; save_json(); return True
        # try direct widget URL if the frame body is empty
        try:
            if len(frame.inner_text('body')) < 40:
                page.goto('https://appleid.apple.com/widget/account/?roleType=Agent&lv=0.4.3&widgetKey=af1139274f266b22b68c2a3e7ad932cb3c0bbe854e13a79af78dcc73136882c3&v=3&appContext=account', wait_until='domcontentloaded', timeout=60000)
                time.sleep(6)
                dump(page, '02_widget_direct')
                n, f, ctl = best(page.frames)
                if f is not None: frame = f
        except Exception as e:
            ev('widget_direct_err', repr(e)[:150])
        ctl = frame_controls(frame)
        ev('controls', ctl[:60])
        open(os.path.join(OUT, 'controls.json'), 'w').write(json.dumps(ctl, indent=1))
        email = (STATE.get('email') or {}).get('addr') or 'probe@example.com'
        nums = STATE.get('numbers') or []
        phone = nums[0]['number'] if nums else ''
        pw = 'Aa1!' + ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(14))
        STATE['password'] = pw
        for step in range(1, 5):
            STATE['stage'] = 'browser_step_%d' % step; save_json()
            txt = ''
            try: txt = frame.inner_text('body')
            except Exception: pass
            cap = captcha_present(txt)
            ev('step_text', {'step': step, 'captcha': cap, 'head': txt[:700]})
            if cap:
                STATE['stage'] = 'captcha_blocked'; STATE['captcha_text'] = txt[:1500]; save_json()
                dump(page, '10_captcha'); return True
            ctl = frame_controls(frame)
            results = {}
            results['first'] = fill_by(frame, ctl, r'first|given', 'Alex')
            results['last'] = fill_by(frame, ctl, r'last|family|surname', 'Miller')
            # birth selects
            for c in ctl:
                if c['tag'] == 'select' and c['vis'] and not c['value']:
                    hay = ' '.join([c['name'], c['id'], c['aria']]).lower()
                    try:
                        sel = ('#' + c['id']) if c['id'] else ('[name="%s"]' % c['name'])
                        if 'month' in hay:
                            frame.locator(sel).first.select_option(index=3, timeout=3000)
                        elif 'day' in hay:
                            frame.locator(sel).first.select_option(index=9, timeout=3000)
                    except Exception:
                        pass
            results['birthday_text'] = (fill_by(frame, ctl, r'year|yyyy', '1990'),
                                        fill_by(frame, ctl, r'\bday\b', '9'),
                                        fill_by(frame, ctl, r'birthday', '09/09/1990'))
            results['email'] = fill_by(frame, ctl, r'email', email)
            results['password'] = fill_by(frame, ctl, r'password', pw)
            results['phone'] = fill_by(frame, ctl, r'phone|mobile|\btel\b', phone)
            ev('fill_results', {'step': step, 'r': {k: str(v) for k, v in results.items()}})
            dump(page, '2%d_step_%d' % (step, step))
            for pat in (r'continue', r'next', r'create account', r'agree', r'create your apple account', r'^create$'):
                r = click_by(frame, ctl, pat)
                if r[0] == 'clicked':
                    ev('clicked', {'step': step, 'pat': pat, 'r': r}); break
            else:
                ev('no_submit_button', {'step': step})
                break
            time.sleep(7)
            info = dump(page, '3%d_after_%d' % (step, step))
            # if a code field appeared -> stop (never guess)
            n2, f2, ctl2 = best(page.frames)
            if f2 is not None: frame = f2
            ctl = frame_controls(frame)
            code_fields = [c for c in ctl if c['tag'] == 'input' and c['vis'] and re.search(r'code|otp', (c['name'] + c['id'] + c['aria'] + c['ph']).lower())]
            if code_fields:
                ev('code_field_appeared', code_fields[:3])
                STATE['stage'] = 'code_field_appeared'; save_json()
                return True
        STATE['stage'] = 'browser_end'; save_json()
        return True

def main():
    STATE['stage'] = 'start'; save_json()
    mailtm_new()
    pub_numbers()
    for entry in (STATE.get('numbers') or [])[:2]:
        inbox_probe(entry)  # baseline single read, before Apple submission
    try:
        browser_attempt()
    except Exception:
        ev('browser_exception', traceback.format_exc()[-1500:])
        STATE['stage'] = 'browser_exception'
    for entry in (STATE.get('numbers') or [])[:2]:
        inbox_probe(entry)  # single read after submission
    msgs = mailtm_fetch()
    STATE['mail_count'] = len(msgs)
    if msgs:
        open(os.path.join(OUT, 'emails.json'), 'w').write(json.dumps(msgs, indent=1, ensure_ascii=False)[:20000])
    save_json()
    log('DONE stage=', STATE['stage'])

if __name__ == '__main__':
    try:
        main()
    except Exception:
        ev('fatal', traceback.format_exc()[-2000:]); save_json()
        raise
