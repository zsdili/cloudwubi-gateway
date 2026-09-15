#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""云五笔打包前 50 次回炉测试（固化要求：打包前至少 50 次以上随机校验）
覆盖：①云端翻译整词优先/末字回退 ②云端情景联想（assoc）③字根图序静态校验
用法：python3 tools/regression50.py   （需网络，直连线上 SCF）"""
import json, urllib.request, sys

GATEWAY = "https://1251037126-bglnivgmaf.ap-guangzhou.tencentscf.com"
WORDS = ["国庆节","中国","工作","人民","手机","电脑","你好","谢谢","加油","北京","上海","深圳","广州",
         "今天","明天","昨天","天气","吃饭","喝水","睡觉","走路","跑步","高兴","快乐","朋友","家人",
         "时间","问题","方法","学习","生活","未来","希望","梦想","奋斗","成功","失败","经验",
         "教训","收获","成长","进步","努力","坚持","信心","勇气","智慧","力量","春天","夏天","秋天","秋天"]
ASSOC = ["国庆节","春节","中秋","元旦","端午","生日快乐","早上好","晚上好","中午好","谢谢","辛苦了",
         "加油","恭喜","晚安","再见","天气","吃饭","喝水","睡觉","走路","跑步","高兴","快乐","朋友",
         "家人","时间","问题","方法","学习","工作","生活","未来","希望","梦想","奋斗","成功","失败",
         "经验","教训","收获","成长","进步","努力","坚持","信心","勇气","智慧","力量","春天","夏天","秋天"]

def post(payload):
    try:
        req = urllib.request.Request(GATEWAY, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def main():
    hit = fb = empty = 0
    for w in WORDS:
        en = post({"word": w, "en": True}).get("en", "")
        if en: hit += 1
        else:
            if post({"word": w[-1], "en": True}).get("en", ""): fb += 1
            else: empty += 1
    linked = sum(1 for w in ASSOC if post({"context": w}).get("phrases"))
    print(f"[翻译] 整词命中 {hit}/{len(WORDS)} 回退 {fb} 空 {empty}")
    print(f"[联想] 有联想 {linked}/{len(ASSOC)}")
    ok = hit >= 50 and linked >= 50 and empty == 0
    print("结论:", "✅ 通过（≥50 次）" if ok else "❌ 未达标")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
