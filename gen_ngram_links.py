#!/usr/bin/env python3
"""从词级训练语料离线生成"上下文→后续词"概率映射表（n-gram 物化版）
过滤标点/功能虚词；保留 2 字+ 实词 + 高频单字衔接词（你/吧/吗）
输出：ngram_link.json {"上文末词|上文末2词": [后续词 top5]}
"""
import json
from collections import Counter, defaultdict

STOP = set("，。！？、；：""''（）《》【】…—·")
FUNC = {"就是","要","很","也","都","的","了","着","过","就","是","和","与","及","为","在","有","个","这","那","对","把","被","向","从","到","跟","比","给","让","用","再","还","又","才","更","最","挺","真","好","想"}
KEEP1 = {"你","我","他","她","它","们","吧","吗","啊","呢","呀","哦"}

def ok(w):
    if not w or w in STOP: return False
    if w in FUNC: return False
    if len(w) == 1 and w not in KEEP1: return False
    return True

bigram = Counter(); trigram = Counter()
with open('/tmp/corpus_tok.txt', encoding='utf-8') as f:
    for line in f:
        toks = ['<s>'] + line.strip().split() + ['</s>']
        for i in range(len(toks)-1): bigram[(toks[i], toks[i+1])] += 1
        for i in range(len(toks)-2): trigram[(toks[i], toks[i+1], toks[i+2])] += 1

links = defaultdict(list)
for (a, b), c in bigram.items():
    if a in ('<s>', '</s>') or b in ('<s>', '</s>') or not ok(b): continue
    links[a].append((b, c))
for (a, b, cc), c in trigram.items():
    if any(x in ('<s>', '</s>') for x in (a, b, cc)) or not ok(cc): continue
    links.setdefault(a + '|' + b, []).append((cc, c))

def topn(lst, n=5):
    return [w for w, c in sorted(lst, key=lambda x: -x[1])[:n]]

out = {k: topn(v) for k, v in links.items()}
with open('ngram_link.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=0)
import os
print(f"映射条数: {len(out)} | 体积: {os.path.getsize('ngram_link.json')} B")
for k in ['前进', '想', '生病了', '学习', '努力', '合作', '天气', '谢谢', '早上好', '辛苦了', '吃饭']:
    print(f"  [{k}] → {out.get(k, '(无)')}")
