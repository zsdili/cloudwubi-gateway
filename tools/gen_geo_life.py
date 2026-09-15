#!/usr/bin/env python3
"""地名/美食/品牌/企业/经典名句 综合词库生成器（可复现资产）
= 全国省市县区（modood 行政区划公开数据）+ 论语名句（chinese-poetry 公开数据）
  + 常见美食/品牌/企业（常备示例，开放贡献扩充）
→ wubi86_geo.txt / wubi86_life.txt / wubi86_classics.txt（追加）
"""
import json, re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phrase_engine import PhraseEngine

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CORPUS = os.path.join(BASE, "corpus")

def load_engine():
    single_dict = {}
    with open(os.path.join(BASE, "wubi86_basic.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) < 2: continue
            single_dict.setdefault(parts[0], []).extend(ord(ch) for w in parts[1:] for ch in w)
    return PhraseEngine(single_dict)

def write_phrases(path, words, engine):
    rows = []
    for w in words:
        try:
            code = engine.phrase_to_code(w)
            if code and len(code) >= 2: rows.append((code, w))
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        for code, w in rows:
            f.write(f"{code} {w}\n")
    return len(rows)

def main():
    engine = load_engine()
    # ① 省市县区（pca.json：{省:{市:[区]}}）
    geo = []
    try:
        d = json.load(open(os.path.join(CORPUS, "pca.json"), encoding="utf-8"))
        for prov, cities in d.items():
            geo.append(prov.replace("省", "").replace("市", "").replace("壮族自治区", "").replace("回族自治区", "").replace("维吾尔自治区", "").replace("自治区", ""))
            geo.append(prov)
            if isinstance(cities, dict):
                for city, dists in cities.items():
                    c = city.replace("市", "").replace("地区", "").replace("自治州", "").replace("盟", "")
                    geo.append(c); geo.append(city)
                    if isinstance(dists, list):
                        for dt in dists:
                            geo.append(dt)
                            geo.append(dt.replace("区", "").replace("县", "").replace("市", "").replace("旗", ""))
    except Exception as e:
        print("pca 解析失败:", e)
    geo = [g for g in dict.fromkeys(geo) if len(g) >= 2]
    n_geo = write_phrases(os.path.join(BASE, "wubi86_geo.txt"), geo, engine)
    print(f"① 地名词库: {n_geo} 条 → wubi86_geo.txt")

    # ② 常见美食/品牌/企业（常备示例 + 开放贡献扩充）
    life = [
        # 八大菜系与名小吃
        "粤菜","川菜","湘菜","鲁菜","苏菜","浙菜","闽菜","徽菜","京菜","东北菜",
        "火锅","麻辣烫","烧烤","烤鸭","小笼包","饺子","面条","米粉","米线","拉面",
        "兰州拉面","沙县小吃","黄焖鸡","肉夹馍","凉皮","煎饼果子","肠粉","早茶","点心",
        "麻辣香锅","酸菜鱼","水煮鱼","宫保鸡丁","麻婆豆腐","回锅肉","鱼香肉丝","糖醋里脊",
        "北京烤鸭","天津狗不理","重庆小面","螺蛳粉","桂林米粉","过桥米线","灌汤包","生煎包",
        "奶茶","咖啡","柠檬茶","珍珠奶茶","杨枝甘露","双皮奶","冰淇淋","蛋糕","面包","蛋挞",
        "苹果","香蕉","橙子","西瓜","葡萄","草莓","樱桃","芒果","榴莲","荔枝",
        "车厘子","蓝莓","猕猴桃","火龙果","山竹","菠萝","柚子","桃子","梨子","橘子",
        # 知名品牌
        "华为","小米","腾讯","阿里巴巴","字节跳动","百度","京东","美团","滴滴","网易",
        "拼多多","快手","抖音","哔哩哔哩","爱奇艺","优酷","唯品会","携程","去哪儿","同程",
        "安踏","李宁","鸿星尔克","特步","361度","波司登","海澜之家","七匹狼","雅戈尔","森马",
        "美的","格力","海尔","海信","TCL","创维","长虹","康佳","奥克斯","方太",
        "老板电器","苏泊尔","九阳","小熊","小米之家","大疆","比亚迪","宁德时代","蔚来","理想",
        "小鹏","吉利","长城","奇瑞","长安","五菱","一汽","上汽","广汽","北汽",
        "农夫山泉","娃哈哈","康师傅","统一","蒙牛","伊利","光明","三元","飞鹤","君乐宝",
        "茅台","五粮液","泸州老窖","洋河","剑南春","汾酒","古井贡","郎酒","习酒","舍得",
        "海天","李锦记","厨邦","恒顺","千禾","太太乐","王守义","老干妈","十三香","涪陵榨菜",
        "中国工商银行","中国建设银行","中国农业银行","中国银行","交通银行","招商银行","平安银行","浦发银行","兴业银行","中信银行",
        "中国移动","中国联通","中国电信","中国石油","中国石化","国家电网","南方电网","中国铁路","中国邮政","中粮集团",
        # 百强企业（常备：中国 500 强常见企业）
        "中石化","中石油","国家电网","中国建筑","中国中铁","中国铁建","中国交建","中国电建","中国中车","中国船舶",
        "中国平安","中国人寿","中国人保","中国太保","新华保险","泰康保险","华夏保险","阳光保险","众安保险","中国再保险",
        "中国银行","工商银行","建设银行","农业银行","交通银行","邮储银行","招商银行","民生银行","光大银行","华夏银行",
        "中国电信","中国联通","中国移动","中国广电","华为","中兴","烽火","大唐","普天","紫光",
        "比亚迪","宁德时代","隆基绿能","通威股份","阳光电源","亿纬锂能","赣锋锂业","天齐锂业","华友钴业","中创新航",
        "中国神华","中煤能源","兖矿能源","陕西煤业","山西焦煤","潞安环能","淮北矿业","平煤股份","山煤国际","华阳股份",
    ]
    life = list(dict.fromkeys(life))
    n_life = write_phrases(os.path.join(BASE, "wubi86_life.txt"), life, engine)
    print(f"② 生活词库: {n_life} 条 → wubi86_life.txt")

    # ③ 论语名句追加（经典词库）
    classics = []
    try:
        d = json.load(open(os.path.join(CORPUS, "lunyu.json"), encoding="utf-8"))
        def extract_sentences(text):
            out = []
            text = re.sub(r'[#*_`>\-\d①-⑩〔〕\[\]（）()「」【】、]', '', text)
            for p in re.split(r'[。！？；\n]', text):
                p = re.sub(r'[，,：:""\'\'·…—]', '', p).strip()
                if 4 <= len(p) <= 24 and re.match(r'^[\u4e00-\u9fff]+$', p):
                    out.append(p)
            return out
        # lunyu.json 可能是 [{"chapter":..., "paragraphs":[...]}]
        for item in d if isinstance(d, list) else []:
            paras = item.get("paragraphs", []) if isinstance(item, dict) else []
            for p in paras:
                classics += extract_sentences(p)
        # 手工精选
        classics += [
            "学而时习之","温故而知新","三人行必有我师","学而不思则罔","思而不学则殆",
            "己所不欲勿施于人","言必行行必果","君子坦荡荡","小人长戚戚","和为贵",
            "知之为知之","不知为不知","见贤思齐","择其善者而从之","敏而好学",
            "不耻下问","三十而立","四十不惑","五十知天命","六十耳顺",
            "有朋自远方来","不亦乐乎","学而不厌","诲人不倦","任重道远",
            "死而后已","三思而后行","欲速则不达","工欲善其事","必先利其器",
            "人无远虑","必有近忧","君子和而不同","小人同而不和","朝闻道夕死可矣",
            "是可忍孰不可忍","过犹不及","不在其位","不谋其政","四海之内皆兄弟",
        ]
    except Exception as e:
        print("论语解析失败:", e)
    # 追加到现有 classics（去重）
    existing = set()
    cl_path = os.path.join(BASE, "wubi86_classics.txt")
    if os.path.exists(cl_path):
        for line in open(cl_path, encoding="utf-8"):
            parts = line.split()
            if len(parts) >= 2: existing.add(parts[1])
    new_cl = [w for w in dict.fromkeys(classics) if w not in existing]
    rows = []
    for w in new_cl:
        try:
            code = engine.phrase_to_code(w)
            if code and len(code) >= 2: rows.append((code, w))
        except Exception:
            pass
    with open(cl_path, "a", encoding="utf-8") as f:
        for code, w in rows:
            f.write(f"{code} {w}\n")
    print(f"③ 经典词库追加: {len(rows)} 条（论语）→ 总计 {len(existing)+len(rows)} 条")

if __name__ == "__main__":
    main()
