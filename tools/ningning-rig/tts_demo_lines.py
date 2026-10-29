# -*- coding: utf-8 -*-
# 官網示範用的寧寧配音：Gemini 文字轉語音（跟 App 同一個聲音 Despina），四語同一段話。
# 用法：python -I tts.py <輸出資料夾> [voice]   鑰匙從 engine/.env.local 讀，不印出來。
import os, sys, wave, re
OUT = sys.argv[1] if len(sys.argv) > 1 else 'p3voice'
VOICE = sys.argv[2] if len(sys.argv) > 2 else 'Despina'
os.makedirs(OUT, exist_ok=True)
key = None
for ln in open('E:/Claude/Munea/engine/.env.local', encoding='utf-8'):
    m = re.match(r'^GEMINI_API_KEY=(.+)$', ln.strip())
    if m: key = m.group(1).strip().strip('"').strip("'")
assert key, 'no GEMINI_API_KEY'
from google import genai
from google.genai import types
client = genai.Client(api_key=key)

LINES = {
    'zh': ('用台灣人平常講話的國語口音，不捲舌、不要北京腔、不要播音腔；語氣溫暖、慢一點，像家人在關心長輩，語尾自然帶一點「喔」「嗎」的感覺。',
           '阿姨早安，昨天晚上有睡好嗎？你上次說膝蓋會痠，今天有好一點嗎？對了，十點要吃血壓的藥喔，時間到我再提醒你一次。'),
    'en': ('Speak warmly and a little slowly, like a caring family member talking to an elderly parent. Natural, friendly, not announcer-like.',
           "Good morning! Did you sleep well last night? You mentioned your knee was aching — is it any better today? Oh, and your blood pressure pill is at ten. I'll remind you again when it's time."),
    'ja': ('年配の家族に話しかけるように、やさしく、少しゆっくり、自然な日本語で。アナウンサー口調にしない。',
           'おはようございます。昨日はよく眠れましたか？この前、膝が痛いとおっしゃっていましたが、今日は少し楽になりましたか？それから、十時に血圧のお薬ですよ。時間になったら、もう一度お声がけしますね。'),
    'es': ('Habla con calidez y un poco despacio, como alguien de la familia que cuida a una persona mayor. Natural, cercano, sin tono de locutor.',
           '¡Buenos días! ¿Durmió bien anoche? Me contó que le dolía la rodilla, ¿hoy está un poco mejor? Ah, y a las diez toca la pastilla de la presión. Se lo vuelvo a recordar cuando sea la hora.'),
}
MODELS = ['gemini-2.5-flash-preview-tts', 'gemini-2.5-pro-preview-tts']

def synth(style, text):
    last = None
    for model in MODELS:
        try:
            r = client.models.generate_content(
                model=model,
                contents=f'{style}\n\n{text}',
                config=types.GenerateContentConfig(
                    response_modalities=['AUDIO'],
                    speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
                ),
            )
            for part in r.candidates[0].content.parts:
                if getattr(part, 'inline_data', None) and part.inline_data.data:
                    return model, part.inline_data.data, part.inline_data.mime_type
            last = 'no audio part'
        except Exception as e:
            last = f'{model}: {type(e).__name__}: {str(e)[:200]}'
    raise SystemExit(last)

for lang, (style, text) in LINES.items():
    model, pcm, mime = synth(style, text)
    rate = 24000
    m = re.search(r'rate=(\d+)', mime or '')
    if m: rate = int(m.group(1))
    p = os.path.join(OUT, f'talk-{lang}.wav')
    with wave.open(p, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    print(lang, model, mime, f'{len(pcm) / 2 / rate:.2f}s', p)
