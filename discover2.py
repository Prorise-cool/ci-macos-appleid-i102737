#!/usr/bin/env python3
"""Discovery 2: from inside the macOS runner, judge whether the planner-designated
public inbox for +1 587 405 6545 (receivesms.co ca-phone-number/23253) is readable,
record its baseline message list; also sample asms.ai free-number inboxes for
reachability and whether any Apple SMS ever lands there. Read-only, no writes."""
import os, re, json, time, traceback
import urllib.request, urllib.error

OUT = os.path.dirname(os.path.abspath(__file__)) + '/out2'
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, 'discover2.log'), 'a', buffering=1)
def log(*a):
    s = ' '.join(str(x) for x in a); print(s); LOG.write(s + '\n')

UAS = {
 'safari': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
 'chrome': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}
def http(url, ua='chrome', timeout=30, headers=None):
    req = urllib.request.Request(url)
    req.add_header('User-Agent', UAS.get(ua, ua))
    req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
    req.add_header('Accept-Language', 'en-US,en;q=0.9')
    for k, v in (headers or {}).items(): req.add_header(k, v)
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return 'ERR', {}, repr(e).encode()

RES = {}
def probe(name, url, ua='chrome'):
    t0 = time.time()
    st, hd, b = http(url, ua=ua)
    txt = b.decode('utf-8', 'replace') if isinstance(b, (bytes, bytearray)) else str(b)
    fn = os.path.join(OUT, name + '.html')
    try: open(fn, 'w').write(txt[:900000])
    except Exception: pass
    low = txt.lower()
    item = {
        'url': url, 'ua': ua, 'status': st, 'len': len(txt), 'secs': round(time.time()-t0, 1),
        'title': (re.search(r'<title[^>]*>(.*?)</title>', txt, re.S | re.I).group(1).strip()[:200]
                  if re.search(r'<title[^>]*>(.*?)</title>', txt, re.S | re.I) else ''),
        'cloudflare': ('just a moment' in low or 'cf-challenge' in low or 'attention required' in low
                       or 'enable javascript and cookies' in low or '/cdn-cgi/challenge' in low),
        'has_apple': 'apple' in low,
        'apple_snippets': [m.group(0) for m in re.finditer(r'.{0,80}[Aa]pple.{0,120}', txt)][:6],
        'has_15874056545': ('15874056545' in txt or '5874056545' in txt or '587-405-6545' in txt or '(587) 405-6545' in txt),
        'has_2833523739': ('2833523739' in txt or '283-352-3739' in txt),
        'waiting': ('waiting on incoming' in low or 'no messages' in low or 'no sms' in low),
        'text_snippet': re.sub(r'\s+', ' ', re.sub(r'<script.*?</script>|<style.*?</style>', ' ', txt, flags=re.S | re.I))[:1500],
    }
    RES[name] = item
    log('[PROBE]', name, st, len(txt), 'cf=', item['cloudflare'], 'apple=', item['has_apple'], 'waiting=', item['waiting'])
    log('   snippet:', item['text_snippet'][:300])
    return item

def main():
    log('start', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    # 1) planner-designated inbox: +15874056545 on receivesms.co
    probe('rs_23253_chrome', 'https://receivesms.co/ca-phone-number/23253/')
    probe('rs_23253_safari', 'https://receivesms.co/ca-phone-number/23253/', ua='safari')
    probe('rs_home', 'https://receivesms.co/')
    # 2) asms.ai samples: one UK number known to have a public inbox, plus a US free number
    probe('asms_uk_447450691467', 'https://asms.ai/number/447450691467')
    probe('asms_us_12093973290', 'https://asms.ai/number/12093973290')
    probe('asms_us_13322566238', 'https://asms.ai/number/13322566238')
    # 3) record any Apple-SMS evidence + message-row samples for the designated inbox
    try:
        t = open(os.path.join(OUT, 'rs_23253_chrome.html')).read()
        rows = re.findall(r'<tr.*?</tr>', t, re.S | re.I)
        RES['rs_rows'] = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' | ', r))[:400] for r in rows[:20]]
        # generic timestamp hits
        RES['rs_times'] = re.findall(r'\b(?:20\d\d-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?|\d{1,2}/\d{1,2}/\d{4}[^\n]{0,10})\b', t)[:20]
    except Exception as e:
        RES['rs_rows_err'] = repr(e)
    json.dump(RES, open(os.path.join(OUT, 'discover2.json'), 'w'), indent=2, ensure_ascii=False)
    log('done')

if __name__ == '__main__':
    try: main()
    except Exception:
        RES['fatal'] = traceback.format_exc()[-2000:]
        json.dump(RES, open(os.path.join(OUT, 'discover2.json'), 'w'), indent=2, ensure_ascii=False)
        log('FATAL', RES['fatal'])
