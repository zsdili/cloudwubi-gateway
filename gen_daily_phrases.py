#!/usr/bin/env python3
"""生成日常高频词组库（jieba 词频数据源，MIT 许可）
过滤：2-4 字、词频≥200、字均在 86 码表（可编码）、排除负面词、去重
输出：wubi86_daily.txt（同 wubi86_phrases.txt 格式：码 词1 词2 ...）
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phrase_engine import PhraseEngine

# 加载单字码表
d = {}
for line in open("wubi86_basic.txt", encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"): continue
    p = line.split()
    if len(p) < 2: continue
    for w in p[1:]:
        if len(w) == 1:
            d.setdefault(p[0], []).append(ord(w))
eng = PhraseEngine(d)

NEG = ("智障","梦魇","前功尽弃","落魄","倒霉","糟糕","失败","完蛋","悲剧","恐怖","灾难","痛苦",
       "绝望","阴暗","沮丧","抑郁","癌症","愚蠢","愚昧","堕落","沉沦","骗子","诈骗","虚伪",
       "丑陋","悲惨","丧气","毁弃","邪恶","犯罪","恐怖袭击","自杀","仇恨","歧视","欺凌","殴打")

# 读 jieba dict.txt（pip 自带词频词典）
jieba_path = "/home/user/.local/lib/python3.12/site-packages/jieba/dict.txt"
rows = []
for line in open(jieba_path, encoding="utf-8"):
    parts = line.strip().split()
    if len(parts) < 3: continue
    w, freq, _ = parts[0], int(parts[1]), parts[2]
    if len(w) < 2 or len(w) > 4: continue
    if freq < 200: continue
    if any(n in w for n in NEG): continue
    rows.append((w, freq))

# 算码（含单字都在码表才保留）
from collections import defaultdict
by_code = defaultdict(list)
miss = 0
for w, freq in rows:
    c = eng.phrase_to_code(w)
    if c and len(c) == 4:
        by_code[c].append((w, freq))
    else:
        miss += 1

# 过滤已在 wubi86_phrases.txt 的词（去重）
existing = set()
for line in open("wubi86_phrases.txt", encoding="utf-8"):
    p = line.strip().split()
    if len(p) >= 2:
        existing.update(p[1:])

lines = []
new_words = 0
for code in sorted(by_code):
    ws = sorted(by_code[code], key=lambda x: -x[1])
    keep = [w for w, f in ws if w not in existing]
    if keep:
        lines.append(code + " " + " ".join(keep))
        new_words += len(keep)

with open("wubi86_daily.txt", "w", encoding="utf-8") as f:
    f.write("# 日常高频词组库（jieba 词频≥200 自动生成，86 全码规则，%d 词）\n" % new_words)
    f.write("\n".join(lines) + "\n")

print(f"jieba 候选: {len(rows)} | 可编码: {sum(len(v) for v in by_code.values())} | 未编码: {miss} | 新增: {new_words}")
import os
print("输出:", os.path.getsize("wubi86_daily.txt"), "B")
