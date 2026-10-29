# -*- coding: utf-8 -*-
"""用 Gemini 生圖（可附參考圖、可做「只改某處」的修圖）。
用法：python gen_gemini.py <輸出.png> <提示詞檔> [--model M] [--aspect 9:16|none] [--size 2K] [參考圖...]
鑰匙從 E:/Claude/Munea/engine/.env.local 的 GEMINI_API_KEY 讀，不印出來。
"""
import base64, json, mimetypes, re, sys, time, urllib.request, urllib.error
args = sys.argv[1:]
model, aspect, size = 'gemini-3-pro-image', '9:16', None
for flag in ('--model', '--aspect', '--size'):
    if flag in args:
        i = args.index(flag); val = args[i + 1]; del args[i:i + 2]
        if flag == '--model': model = val
        elif flag == '--aspect': aspect = val
        else: size = val
out, prompt_file, refs = args[0], args[1], args[2:]
key = None
for line in open('E:/Claude/Munea/engine/.env.local', encoding='utf-8'):
    m = re.match(r'^GEMINI_API_KEY\s*=\s*"?([^"\s]+)"?', line.strip())
    if m: key = m.group(1)
if not key: sys.exit('no GEMINI_API_KEY')
parts = [{'inline_data': {'mime_type': mimetypes.guess_type(r)[0] or 'image/png',
                          'data': base64.b64encode(open(r, 'rb').read()).decode()}} for r in refs]
parts.append({'text': open(prompt_file, encoding='utf-8').read()})
body = {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'responseModalities': ['IMAGE']}}
cfg = {}
if aspect != 'none': cfg['aspectRatio'] = aspect
if size: cfg['imageSize'] = size
if cfg: body['generationConfig']['imageConfig'] = cfg
url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
t0 = time.time()
try:
    resp = json.load(urllib.request.urlopen(req, timeout=300))
except urllib.error.HTTPError as e:
    sys.exit(f'HTTP {e.code}: ' + e.read().decode(errors='replace')[:400])
for cand in resp.get('candidates', []):
    for p in (cand.get('content') or {}).get('parts', []):
        data = (p.get('inline_data') or p.get('inlineData') or {}).get('data')
        if data:
            open(out, 'wb').write(base64.b64decode(data)); print(out, round(time.time() - t0), 's'); sys.exit(0)
sys.exit('NO IMAGE: ' + json.dumps(resp)[:500])
