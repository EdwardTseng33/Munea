# -*- coding: utf-8 -*-
import re
p='tandelo-proposal.html'; s=open(p,encoding='utf-8').read()
css = open('_restyle.css',encoding='utf-8').read()
s=re.sub(r'<style>.*?</style>','<style>\n'+css+'\n</style>',s,count=1,flags=re.S)
if '<meta charset' not in s:
    s=s.replace('<title>Tandelo 提案</title>','<meta charset="utf-8">\n<title>Tandelo 提案</title>',1)
s=s.replace('family=Sora:wght@500;600;700;800&family=Noto+Sans+TC:wght@400;500;700','family=Sora:wght@500;600;700;800&family=Noto+Serif+TC:wght@600;700&family=Noto+Sans+TC:wght@400;500;700')
# small grey paragraphs -> .note
s=re.sub(r'<p style="font-size:1[12](?:\.5)?px;color:var\(--mute\);margin:[^"]*">','<p class="note">',s)
s=s.replace('font-size:12.5px;margin:0">品類不是','font-size:14.5px;margin:0">品類不是')
s=s.replace("font-family:Sora,'Noto Sans TC';font-weight:800;font-size:14px;margin:0 0 4px","font-family:Sora,'Noto Sans TC';font-weight:800;font-size:17px;line-height:1.5;margin:0 0 6px;color:var(--ink)")
s=s.replace('<p style="font-size:13px;margin:0 0 6px"><b>三年遠景</b>','<p><b>三年遠景</b>')
s=s.replace('<table style="margin-top:6px">','<table style="margin-top:10px">')
s=s.replace('<div style="display:grid;grid-template-columns:1fr 1fr;gap:3px 16px;font-size:12px">','<div class="gloss">')
s=s.replace('<div class="box" style="background:var(--bg)"><h4>本案用語，先講清楚</h4>','<div class="box" style="background:var(--tint)"><h4>本案用語，先講清楚</h4>')
# page anchors
if 'id="p1"' not in s:
    ids=['p1','p2','p3','p4','p5','p6']
    parts=s.split('<div class="page">')
    s=parts[0]+''.join('<div class="page" id="%s">%s'%(ids[i],parts[i+1]) for i in range(len(parts)-1))
# cover + toc
if 'class="cover"' not in s:
    cover = open('_cover.html',encoding='utf-8').read()
    s=s.replace('<div class="deck">\n','<div class="deck">\n\n'+cover+'\n',1)
# wrap tables
if 'class="scroll"' not in s:
    s=re.sub(r'(<table\b.*?</table>)',r'<div class="scroll">\1</div>',s,flags=re.S)
open(p,'w',encoding='utf-8').write(s)
print('divs',s.count('<div'),s.count('</div>'),'pages',s.count('class="page"'))
