import urllib.request, os
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15'
op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
os.makedirs('out6', exist_ok=True)
for u in ['https://asms.ai/number/447450699185','https://asms.ai/number/447481726578','https://receivesms.co/ca-phone-number/23253/']:
    try:
        r=urllib.request.Request(u); r.add_header('User-Agent',UA)
        with op.open(r,timeout=25) as x: b=x.read(); print(u,x.status,len(b))
        open('out6/inbox_after_'+u.rstrip('/').split('/')[-1]+'.html','wb').write(b)
    except Exception as e: print(u,'ERR',repr(e)[:160])
