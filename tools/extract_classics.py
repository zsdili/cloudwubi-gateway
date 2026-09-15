#!/usr/bin/env python3
"""经典名句词库生成器（可复现资产）
= 孙子兵法十三篇 + 毛泽东选集精选名篇 → 精选名句 → wubi86_classics.txt
来源：孙子兵法 GitHub lincome/szbf；毛选 GitHub lansepeach/maoxuan（公开文本）
用途：输入法词组库（经典语句可打出），不参与 n-gram 联想训练（文言与日常语境差异大）
"""
import json, re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phrase_engine import PhraseEngine

# ① 手工精选知名名句
CLASSICS = [
    # 孙子兵法
    "知己知彼","百战不殆","不战而屈人之兵","攻其无备","出其不意","上兵伐谋",
    "兵贵神速","置之死地而后生","以逸待劳","声东击西","兵不厌诈","运筹帷幄",
    "胜败乃兵家常事","先发制人","避实击虚","知己知彼百战不殆","将在外君命有所不受",
    "兵者诡道也","善战者致人而不致于人","以正合以奇胜","知彼知己胜乃不殆",
    "投之亡地然后存陷之死地然后生","围魏救赵","远交近攻","调虎离山","欲擒故纵",
    "擒贼先擒王","十则围之","倍则分之","攻心为上","兵马未动粮草先行",
    # 毛选名句（公开经典名句，词库用途）
    "为人民服务","实事求是","星星之火可以燎原","自力更生","艰苦奋斗",
    "反对本本主义","愚公移山","没有调查就没有发言权","实践出真知",
    "团结就是力量","一切从实际出发","具体问题具体分析","理论联系实际",
    "批评与自我批评","谦虚使人进步","骄傲使人落后","群众路线",
    "全心全意为人民服务","革命不是请客吃饭","榜样的力量是无穷的",
    "好好学习天天向上","枪杆子里面出政权","农村包围城市",
    "雄关漫道真如铁","人间正道是沧桑","敢教日月换新天",
    "宜将剩勇追穷寇","不可沽名学霸王","世上无难事只要肯登攀",
    "一万年太久只争朝夕","数风流人物还看今朝","不到长城非好汉",
]

def extract_sentences(text):
    out = []
    text = re.sub(r'[#*_`>\-\d①-⑩〔〕\[\]（）()「」【】、]', '', text)
    for p in re.split(r'[。！？；\n]', text):
        p = re.sub(r'[，,：:""\'\'·…—]', '', p).strip()
        if 4 <= len(p) <= 24 and re.match(r'^[\u4e00-\u9fff]+$', p):
            out.append(p)
    return out

def clean(l):
    out = []
    for s in l:
        if not (4 <= len(s) <= 12): continue
        if re.match(r'^[\u4e00-\u9fff]+$', s) and not re.search(r'十九|一九四|一九|年月|第[一二三四五六七八九十]', s):
            out.append(s)
    return out

def main():
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "corpus")
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    classics = list(CLASSICS)
    added = set(classics)
    def take(l, n):
        r = []
        for s in l:
            if s in added: continue
            added.add(s); r.append(s)
            if len(r) >= n: break
        return r
    # 孙子兵法自动补
    sz = []
    for f in os.listdir(os.path.join(base, "sunzi")):
        if f.endswith(".md") and os.path.getsize(os.path.join(base, "sunzi", f)) > 100:
            sz += extract_sentences(open(os.path.join(base, "sunzi", f), encoding="utf-8").read())
    classics += take(clean(sz), 150)
    # 毛选自动补
    mx = []
    for f in os.listdir(os.path.join(base, "maoxuan")):
        if f.endswith(".md"):
            mx += extract_sentences(open(os.path.join(base, "maoxuan", f), encoding="utf-8").read())
    classics += take(clean(mx), 100)
    classics = list(dict.fromkeys(classics))

    # 从 wubi86_basic.txt 构建 编码→码点 字典（PhraseEngine 正向字典格式）
    single_dict = {}
    with open(os.path.join(repo, "wubi86_basic.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) < 2: continue
            code = parts[0]
            single_dict.setdefault(code, []).extend(ord(ch) for w in parts[1:] for ch in w)
    engine = PhraseEngine(single_dict)
    ok, fail = [], []
    for w in classics:
        try:
            code = engine.phrase_to_code(w)
            if code and len(code) >= 2: ok.append((w, code))
            else: fail.append(w)
        except Exception:
            fail.append(w)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "wubi86_classics.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        for w, code in ok:
            f.write(f"{code} {w}\n")
    print(f"经典词库: {len(ok)} 条（无码 {len(fail)}）→ {out_path}")
    return ok

if __name__ == "__main__":
    main()
