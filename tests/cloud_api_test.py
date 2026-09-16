#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云五笔 · 云端接口 60+ 用例测试矩阵（真实线上 SCF，非模拟器）
   发布门禁：全绿才可发布。运行: python3 cloud_api_test.py"""
import json, urllib.request, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

G = "https://1251037126-bglnivgmaf.ap-guangzhou.tencentscf.com"

def post(payload, retries=3):
    """带重试的 POST（SCF 瞬时限流 429/434/5xx → 退避重试，防误报）"""
    for i in range(retries):
        req = urllib.request.Request(G, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return 200, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 434, 500, 502, 503) and i < retries - 1:
                import time; time.sleep(3 + i * 3); continue
            return e.code, {}
        except Exception as e:
            if i < retries - 1:
                import time; time.sleep(3 + i * 3); continue
            return -1, {"_error": str(e)}
    return -1, {}

passed, failed, rows = 0, [], []

def check(name, payload, expect, mode="contains"):
    """expect: 期望的首候选/期望空/期望含。mode: contains(首候选含) / empty / noerror / en_contains"""
    global passed
    code, d = post(payload)
    ok = False; msg = ""
    if code != 200:
        msg = f"HTTP {code}"
    elif mode == "noerror":
        ok = True; msg = "无异常"
    elif mode == "empty":
        got = d.get("phrases", d.get("en", ""))
        ok = (got in ([], "", None)); msg = f"空=OK" if ok else f"应空实得:{str(got)[:30]}"
    elif mode == "en_contains":
        en = d.get("en", "")
        ok = bool(en) and expect in en
        msg = f"en={en[:50]}" if en else "en=空"
    else:
        got = d.get("phrases", []) if isinstance(d.get("phrases"), list) else []
        first = got[0] if got else ""
        cands = got[:3]
        ok = (expect in cands); msg = f"前3:{'|'.join(str(x) for x in cands)[:60]}" if cands else "空"
        if not ok and mode == "contains":
            ok = any(expect in str(x) for x in cands)
    rows.append((name, "✅" if ok else "❌", msg))
    if ok: passed += 1
    else: failed.append((name, payload, expect, msg))

# ============ A. 情景会话联想（整句优先，context 接口）35 例 ============
A = [
    ("山重水复疑无路","柳暗花明又一村"),("哑巴吃黄连","有苦说不出"),("在干嘛","在想事情"),
    ("辛苦了","钟总您好"),("早上好","早上好呀"),("床前明月光","疑是地上霜"),("竹篮打水","一场空"),
    ("八仙过海","各显神通"),("外甥打灯笼","照旧"),("芝麻开花","节节高"),("打破砂锅","问到底"),
    ("塞翁失马","焉知非福"),("亡羊补牢","为时不晚"),("知己知彼","百战不殆"),("星星之火","可以燎原"),
    ("少壮不努力","老大徒伤悲"),("欲穷千里目","更上一层楼"),("春眠不觉晓","处处闻啼鸟"),
    ("谁知盘中餐","粒粒皆辛苦"),("两个黄鹂鸣翠柳","一行白鹭上青天"),("不识庐山真面目","只缘身在此山中"),
    ("会当凌绝顶","一览众山小"),("但愿人长久","千里共婵娟"),("先天下之忧而忧","后天下之乐而乐"),
    ("天若有情天亦老","人间正道是沧桑"),("雄关漫道真如铁","而今迈步从头越"),("落霞与孤鹜齐飞","秋水共长天一色"),
    ("沉舟侧畔千帆过","病树前头万木春"),("酒逢知己千杯少","话不投机半句多"),("路遥知马力","日久见人心"),
    ("宝剑锋从磨砺出","梅花香自苦寒来"),("只要功夫深","铁杵磨成针"),("世上无难事","只怕有心人"),
    ("读万卷书","行万里路"),("听君一席话","胜读十年书"),
]
for ctx, exp in A:
    check(f"A-联想 {ctx[:8]}", {"context": ctx}, exp)

# ============ B. 边界/异常 15 例 ============
B = [
    ("B-空文本","", "empty"), ("B-单字好","好", "noerror"), ("B-单字爱","爱", "noerror"),
    ("B-二字前进","前进", "noerror"), ("B-数字123","123", "empty"), ("B-英文hello","hello", "empty"),
    ("B-符号","！", "empty"), ("B-长句9字","床前明月光疑是地上霜", "noerror"),
    ("B-超长30字","今天天气很好我们一起去公园散步聊天吃饭开心每一天", "noerror"),
    ("B-混合中英数","我吃了2个apple", "noerror"), ("B-不存在词xyz","xyzabc", "noerror"),
    ("B-特殊字符","@#$%^&*", "empty"), ("B-重复字","好好好", "noerror"), ("B-天气","天气", "noerror"),
    ("B-吃饭了吗","吃饭了吗", "noerror"),
]
for name, ctx, mode in B:
    check(name, {"context": ctx}, None, mode)

# ============ C. 翻译降级链（en）15 例 ============
C = [
    ("C-翻译 国庆节", {"word":"国庆节","en":True,"words":["是国庆节","国庆节","庆节","节"]}, "PRC", "en_contains"),
    ("C-翻译 五笔", {"word":"五笔","en":True,"words":["五笔","笔"]}, "", "noerror"),
    ("C-翻译 苹果", {"word":"苹果","en":True,"words":["苹果","果"]}, "", "noerror"),
    ("C-翻译 电脑", {"word":"电脑","en":True,"words":["电脑","脑"]}, "", "noerror"),
    ("C-翻译 手机", {"word":"手机","en":True,"words":["手机","机"]}, "", "noerror"),
    ("C-翻译 天气", {"word":"天气","en":True,"words":["天气","气"]}, "", "noerror"),
    ("C-翻译 你好", {"word":"你好","en":True,"words":["你好","好"]}, "", "noerror"),
    ("C-翻译 钟单字", {"word":"钟","en":True}, "", "noerror"),
    ("C-翻译 数字123", {"word":"123","en":True}, "", "empty"),
    ("C-翻译 英文hello", {"word":"hello","en":True}, "", "empty"),
    ("C-翻译 空", {"word":"","en":True}, "", "empty"),
    ("C-翻译 混合abc钟", {"word":"abc钟","en":True,"words":["abc钟","钟"]}, "", "noerror"),
    ("C-翻译 生僻魑魅", {"word":"魑魅","en":True,"words":["魑魅","魅"]}, "", "noerror"),
    ("C-翻译 节日", {"word":"节日","en":True,"words":["节日","日"]}, "", "noerror"),
    ("C-翻译 输入法", {"word":"输入法","en":True,"words":["输入法","法"]}, "", "noerror"),
]
for name, payload, exp, mode in C:
    check(name, payload, exp, mode)

# ============ 输出矩阵 ============
print(f"\n{'='*78}\n总用例: {len(A)+len(B)+len(C)}  通过: {passed}  失败: {len(failed)}")
print(f"{'='*78}")
print(f"{'用例':<28}{'结果':<6}实际")
for name, ok, msg in rows:
    print(f"{name:<28}{ok:<6}{msg}")
if failed:
    print(f"\n❌ 失败明细:")
    for name, payload, expect, msg in failed:
        print(f"  {name}: 期望[{expect}] 实际[{msg}] payload={json.dumps(payload,ensure_ascii=False)[:80]}")
else:
    print(f"\n✅ 全绿（{len(A)+len(B)+len(C)}/{len(A)+len(B)+len(C)}）—— 可发布")
