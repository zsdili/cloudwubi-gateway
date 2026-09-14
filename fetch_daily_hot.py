#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云五笔 每日热词自动入库脚本（v0.5.33 固化机制）
用法：
  python3 fetch_daily_hot.py 热词1 热词2 ...    # 传入今日热词，自动 86 规则算码
  python3 fetch_daily_hot.py --file hot.txt     # 从文件读取（每行一词）
输出：daily_hot_words.json（云端加载层）；随后运行 deploy_scf.py 完成部署
"""
import json, os, re, sys

BASE = os.path.join(os.path.dirname(__file__), "..", "cloudwubi-client")
SINGLE = os.path.join(BASE, "android", "app", "src", "main", "assets", "wubi_single.txt")

def load_single():
    single = {}
    for line in open(SINGLE, encoding="utf-8"):
        line = line.strip()
        if not line: continue
        i = 0
        while i < len(line) and 'a' <= line[i] <= 'y': i += 1
        if i <= 0 or i >= len(line) or i > 4: continue
        code, rest = line[:i], line[i:].strip()
        for w in rest.split():
            if len(w) == 1 and (w not in single or len(code) > len(single[w])):
                single[w] = code
    return single

def code86(single, w):
    w = re.sub(r'[^\u4e00-\u9fff]', '', w)
    if len(w) == 1: return single.get(w, '')
    if len(w) == 2: return (single.get(w[0],'')[:2] + single.get(w[1],'')[:2])[:4]
    if len(w) == 3: return (single.get(w[0],'')[:1] + single.get(w[1],'')[:1] + single.get(w[2],'')[:2])[:4]
    return (single.get(w[0],'')[:1] + single.get(w[1],'')[:1] + single.get(w[2],'')[:1] + single.get(w[-1],'')[:1])[:4]

def main():
    words = sys.argv[1:]
    if words and words[0] == '--file':
        words = [l.strip() for l in open(words[1], encoding='utf-8') if l.strip()]
    if not words:
        print("用法: python3 fetch_daily_hot.py 热词1 热词2 ..."); return 1
    single = load_single()
    out, missing = {}, []
    for w in words:
        c = code86(single, w)
        if len(c) == 4 and all('a' <= x <= 'y' for x in c):
            out[w] = c
        else:
            missing.append((w, c))
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "daily_hot_words.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ 入库 {len(out)} 词 → daily_hot_words.json")
    for w, c in missing: print(f"⚠️  算码失败（字根缺失，可补基础库后重跑）: {w} = {c}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
