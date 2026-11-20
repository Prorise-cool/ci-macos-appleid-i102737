#!/usr/bin/env python3
"""Redact secrets from out7 before artifact upload: Apple password, temp-mail address,
mail.tm JWT / guerrilla sid, and any 6-digit code fields. Stage/evidence kept."""
import os, re, json
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out8')
SECRET_KEYS = {'pw', 'password', 'token', 'sid', 'email_code', 'sms_code'}
PLACE = '<REDACTED>'
def redact_obj(o):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k in SECRET_KEYS:
                o[k] = PLACE
            elif k in ('addr', 'email_addr') and isinstance(v, str):
                o[k] = '<MAILBOX_REDACTED>'
            else:
                redact_obj(v)
    elif isinstance(o, list):
        for x in o: redact_obj(x)
p = os.path.join(OUT, 'summary8.json')
if os.path.exists(p):
    try:
        j = json.load(open(p)); redact_obj(j); json.dump(j, open(p, 'w'), indent=2, ensure_ascii=False)
        print('redacted', p)
    except Exception as e: print('summary redact err', e)
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
JWT_RE = re.compile(r'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}')
for name in os.listdir(OUT):
    if not (name.endswith('.txt') or name.endswith('.log') or name.endswith('.json')):
        continue
    fp = os.path.join(OUT, name)
    try:
        s = open(fp, errors='replace').read()
        s2 = EMAIL_RE.sub('<MAILBOX_REDACTED>', s)
        s2 = JWT_RE.sub('<JWT_REDACTED>', s2)
        if s2 != s: open(fp, 'w').write(s2); print('scrubbed', name)
    except Exception as e: print('scrub err', name, e)
print('done')
