#!/usr/bin/env python3
"""
沐寧 Munea · 本機測試伺服器 — 在瀏覽器真的跟寧寧對話。
接上 chat_engine：她的腦＋記憶＋主動開口＋Leda 的聲音。
用法：GEMINI_API_KEY="..." py server.py  → 瀏覽器開 http://localhost:8200
"""
import os, sys, json, base64, io, wave, time
from http.server import BaseHTTPRequestHandler, HTTPServer
import chat_engine as eng
from google.genai import types

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("需要 GEMINI_API_KEY")


def reply_conv(history):
    """帶完整對話脈絡，用寧寧的腦＋記憶回話。"""
    c = eng.CHARS["寧寧"]
    sys_i = c["persona"] + eng.RED + eng._profile_ctx()
    contents = [types.Content(role=h["role"], parts=[types.Part(text=h["text"])]) for h in history]
    for _ in range(4):
        for m in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
            try:
                r = eng.client.models.generate_content(
                    model=m, contents=contents,
                    config=types.GenerateContentConfig(system_instruction=sys_i, temperature=0.85))
                return r.text.strip()
            except Exception:
                pass
        time.sleep(2)
    return "（不好意思，我這邊連線有點不順，等一下再陪你好不好？）"


def tts_b64(text, voice="Leda"):
    for m in ("gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"):
        try:
            r = eng.client.models.generate_content(
                model=m, contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
            pcm = r.candidates[0].content.parts[0].inline_data.data
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            return base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
    return ""


PAGE = """<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>跟寧寧聊聊</title>
<style>
 :root{--teal:#3AA8A0;--teal-d:#2E8A83;--cream:#F4F0E8;--ink:#3A352E;--mint:#E5F0EE}
 *{box-sizing:border-box;margin:0;padding:0;font-family:"Noto Sans TC",system-ui,sans-serif}
 body{background:var(--cream);color:var(--ink);height:100vh;display:flex;flex-direction:column;max-width:480px;margin:0 auto}
 header{background:var(--teal-d);color:#fff;padding:14px 18px;display:flex;align-items:center;gap:12px}
 header .av{width:40px;height:40px;border-radius:50%;background:var(--teal);display:grid;place-items:center;font-size:20px}
 header b{font-size:18px}header small{opacity:.85;font-size:12px;display:block}
 #log{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px}
 .b{max-width:80%;padding:11px 15px;border-radius:18px;line-height:1.6;font-size:15.5px;white-space:pre-wrap}
 .me{align-self:flex-end;background:var(--teal);color:#fff;border-bottom-right-radius:5px}
 .ne{align-self:flex-start;background:#fff;border-bottom-left-radius:5px;box-shadow:0 2px 8px rgba(0,0,0,.06)}
 .ne .play{cursor:pointer;color:var(--teal-d);font-size:13px;margin-top:6px;display:inline-block}
 .typing{align-self:flex-start;color:#999;font-size:14px;padding:6px 15px}
 footer{padding:12px;display:flex;gap:8px;background:#fff;border-top:1px solid #eee}
 input{flex:1;border:1.5px solid #e3ddd2;border-radius:999px;padding:11px 16px;font-size:15px;outline:none}
 input:focus{border-color:var(--teal)}
 button{border:none;background:var(--teal-d);color:#fff;border-radius:999px;padding:0 20px;font-size:15px;font-weight:700;cursor:pointer}
</style></head><body>
<header><div class="av">🌸</div><div><b>寧寧</b><small>智慧照護陪伴 · 測試版</small></div></header>
<div id="log"></div>
<footer><button id="mic" title="用說的">🎤</button><input id="msg" placeholder="跟寧寧說說話…" autocomplete="off"><button id="send">送出</button></footer>
<script>
const log=document.getElementById('log'),inp=document.getElementById('msg'),btn=document.getElementById('send');
let history=[], audioUnlocked=false;
function bubble(text,who,audio){
  const d=document.createElement('div');d.className='b '+(who==='me'?'me':'ne');d.textContent=text;
  if(who==='ne'&&audio){const p=document.createElement('span');p.className='play';p.textContent='🔊 點我聽寧寧說';
    p.onclick=()=>play(audio);d.appendChild(document.createElement('br'));d.appendChild(p);
    if(audioUnlocked)play(audio);}
  log.appendChild(d);log.scrollTop=log.scrollHeight;
}
function play(b64){try{const a=new Audio('data:audio/wav;base64,'+b64);a.play();audioUnlocked=true;}catch(e){}}
function typing(on){let t=document.getElementById('tp');if(on&&!t){t=document.createElement('div');t.id='tp';t.className='typing';t.textContent='寧寧打字中…';log.appendChild(t);log.scrollTop=log.scrollHeight;}if(!on&&t)t.remove();}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json();}
async function send(){const m=inp.value.trim();if(!m)return;inp.value='';bubble(m,'me');history.push({role:'user',text:m});audioUnlocked=true;typing(true);
  const r=await post('/chat',{history});typing(false);bubble(r.reply,'ne',r.audio);history.push({role:'model',text:r.reply});}
btn.onclick=send;inp.onkeydown=e=>{if(e.key==='Enter')send();};
const mic=document.getElementById('mic');const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
if(SR){mic.onclick=()=>{const r=new SR();r.lang='zh-TW';mic.textContent='🔴';audioUnlocked=true;r.onresult=e=>{inp.value=e.results[0][0].transcript;send();};r.onend=()=>mic.textContent='🎤';r.start();};}else{mic.style.display='none';}
(async()=>{typing(true);const r=await post('/open',{});typing(false);bubble(r.reply,'ne',r.audio);history.push({role:'model',text:r.reply});})();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            b = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(ln) or "{}")
        if self.path == "/open":
            t = eng.open_chat()
            self._json({"reply": t, "audio": tts_b64(t)})
        elif self.path == "/chat":
            t = reply_conv(data.get("history", []))
            self._json({"reply": t, "audio": tts_b64(t)})
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    print("沐寧測試伺服器啟動 → http://localhost:8200  （Ctrl+C 結束）")
    HTTPServer(("127.0.0.1", 8200), H).serve_forever()
