#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云五笔 每日热词自动入库（v0.5.64 固化）：百度热榜+头条热榜 → 过滤 → jieba 分词 → 86 码 → daily_hot_words.json
用法: python3 fetch_hot_daily.py [--deploy] [SecretId SecretKey]
安全过滤: 涉政/领导人/负面/灾害词一律剔除,只收阳光积极热词"""
import json, re, os, sys, urllib.request, jieba

BASE = os.path.dirname(os.path.abspath(__file__))
SINGLE_TXT = os.path.join(BASE, "wubi86_basic.txt")
HOT_JSON = os.path.join(BASE, "daily_hot_words.json")

BLACK = ["习近平","总书记","国家主席","国务院总理","政协","人大","政治局","领导人","复信","致辞","贺电","会见","考察","调研",
         "外交部","国防部","台独","两岸","中美","俄乌","巴以","以色列","哈马斯","乌克兰","俄罗斯","特朗普","拜登","普京","泽连斯基",
         "朝鲜","金正恩","伊朗","战争","冲突","抗议","游行","示威","反腐","落马","审查","纪委","监委","死刑","判决","庭审","被捕",
         "拘留","事故","死亡","遇难","爆炸","枪击","袭击","恐怖","病毒","疫情","确诊","感染","封控","隔离","暴跌","崩盘","加息",
         "地震","台风","洪灾","火灾","坠机","车祸","中毒","诈骗","拐卖","性侵","猥亵","自杀","跳楼","受贿","获刑","被判","立案",
         "罚款","处罚","罢工","裁员","违约","造假","塌方","滑坡","溺水","失联","纠纷","起诉","举报","投诉","腐败","失职",
         "道歉","争议","翻车","打假","辟谣","不实","质疑","查处","违规","曝光","维权"]
def is_black(t): return any(b in t for b in BLACK)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.read().decode("utf-8","ignore")
    except Exception: return ""

def load_single():
    s = {}
    for line in open(SINGLE_TXT, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"): continue
        i = 0
        while i < len(line) and "a" <= line[i] <= "y": i += 1
        if i <= 0 or i >= len(line): continue
        code, chars = line[:i], line[i:].strip()
        for w in chars.split():
            if len(w) == 1 and (w not in s or len(code) > len(s[w])): s[w] = code
    return s

def code86(single, w):
    w = re.sub(r"[^\u4e00-\u9fff]", "", w)
    if not w: return ""
    if len(w) == 1: return single.get(w, "")
    if len(w) == 2:
        a, b = single.get(w[0],""), single.get(w[1],"")
        return (a[:2]+b[:2])[:4] if a and b else ""
    if len(w) == 3:
        a, b, c = single.get(w[0],""), single.get(w[1],""), single.get(w[2],"")
        return (a[:1]+b[:1]+c[:2])[:4] if a and b and c else ""
    a, b, c, z = (single.get(w[i],"") for i in (0,1,2,-1))
    return (a[:1]+b[:1]+c[:1]+z[:1])[:4] if a and b and c and z else ""

def main():
    titles = []
    bd = get("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    try:
        for card in json.loads(bd).get("data",{}).get("cards",[]):
            for c in card.get("content",[]):
                for it in c.get("content",[]):
                    w = it.get("word","")
                    if w and not is_black(w): titles.append(w)
    except Exception: pass
    tt = get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    try:
        for it in json.loads(tt).get("data",[]):
            t = it.get("Title","")
            if t and not is_black(t): titles.append(t)
    except Exception: pass

    phrases = []
    for t in titles:
        t2 = re.sub(r"[^\u4e00-\u9fff]", "", t)
        if not t2 or len(t2) < 2: continue
        words = [w for w in jieba.cut(t2) if 2 <= len(w) <= 6]
        phrases.extend(words if words else ([t2] if len(t2) <= 6 else []))
    for t in titles:
        t2 = re.sub(r"[^\u4e00-\u9fff]", "", t)
        if 2 <= len(t2) <= 8: phrases.append(t2)
    phrases = list(dict.fromkeys(p for p in phrases if len(p) >= 2 and not is_black(p)))

    single = load_single()
    hot = {}
    try: hot = json.load(open(HOT_JSON, encoding="utf-8"))
    except Exception: hot = {}
    added = []
    for w in phrases:
        c = code86(single, w)
        if c and w not in hot:
            hot[w] = c
            added.append(w)
        if len(hot) >= 120: break
    # v0.5.104-fix 封顶 120：超限时保留最新 120 条（热词有时效，最旧挤出），去重不误删旧词
    if len(hot) > 120:
        hot = dict(list(hot.items())[-120:])
    json.dump(hot, open(HOT_JSON, "w"), ensure_ascii=False, indent=1)
    print(f"热词入库完成: {len(hot)} 条, 新增 {len(added)} 条: {added[:10]}")

if __name__ == "__main__":
    main()
