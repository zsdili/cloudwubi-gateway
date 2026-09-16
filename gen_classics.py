#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.7.x 云端经典语料扩充：毛选名句 + 唐诗宋词 + 歇后语（公开文献/民间熟语，安全中性）
   按 86 五笔构词公式生成编码，合并进 wubi86_classics.txt"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASIC = "wubi86_basic.txt"
CLASSICS = "wubi86_classics.txt"

# 构建 单字 -> 全码（重码取第一个）
char_to_code = {}
for line in open(BASIC, encoding="utf-8"):
    parts = line.split()
    if len(parts) >= 2 and parts[1] and parts[1] not in char_to_code:
        char_to_code[parts[1]] = parts[0]

def phrase_to_code(phrase):
    chars = list(phrase)
    n = len(chars)
    codes = []
    for ch in chars:
        if ch not in char_to_code:
            return None
        codes.append(char_to_code[ch])
    if n == 1:
        return codes[0]
    elif n == 2:
        return codes[0][:2] + codes[1][:2]
    elif n == 3:
        return codes[0][:1] + codes[1][:1] + codes[2][:2]
    else:
        return codes[0][:1] + codes[1][:1] + codes[2][:1] + codes[-1][:1]

NEW = [
    # 毛选/毛泽东诗词经典名句（公开文献，正能量）
    "星星之火可以燎原", "为人民服务", "实事求是", "没有调查就没有发言权",
    "一切反动派都是纸老虎", "自力更生艰苦奋斗", "谦虚使人进步骄傲使人落后",
    "好好学习天天向上", "战略上藐视敌人战术上重视敌人", "农村包围城市武装夺取政权",
    "不打无准备之仗", "军民团结如一人试看天下谁能敌", "宜将剩勇追穷寇不可沽名学霸王",
    "数风流人物还看今朝", "世上无难事只要肯登攀", "一万年太久只争朝夕",
    "天若有情天亦老人间正道是沧桑", "雄关漫道真如铁而今迈步从头越",
    # 唐诗宋词名句（文学常识）
    "会当凌绝顶一览众山小", "欲穷千里目更上一层楼", "海内存知己天涯若比邻",
    "春眠不觉晓处处闻啼鸟", "野火烧不尽春风吹又生", "谁知盘中餐粒粒皆辛苦",
    "两个黄鹂鸣翠柳一行白鹭上青天", "飞流直下三千尺疑是银河落九天",
    "朝辞白帝彩云间千里江陵一日还", "孤帆远影碧空尽唯见长江天际流",
    "春风又绿江南岸明月何时照我还", "不识庐山真面目只缘身在此山中",
    "山重水复疑无路柳暗花明又一村", "等闲识得东风面万紫千红总是春",
    "劝君更尽一杯酒西出阳关无故人", "洛阳亲友如相问一片冰心在玉壶",
    "葡萄美酒夜光杯欲饮琵琶马上催", "醉卧沙场君莫笑古来征战几人回",
    "少壮不努力老大徒伤悲", "一寸光阴一寸金寸金难买寸光阴",
    "书山有路勤为径学海无涯苦作舟", "但愿人长久千里共婵娟",
    "大江东去浪淘尽千古风流人物", "莫等闲白了少年头空悲切",
    "先天下之忧而忧后天下之乐而乐", "落霞与孤鹜齐飞秋水共长天一色",
    "沉舟侧畔千帆过病树前头万木春", "山穷水尽疑无路柳暗花明又一村",
    # 歇后语（民间熟语）
    "竹篮打水一场空", "肉包子打狗有去无回", "哑巴吃黄连有苦说不出",
    "外甥打灯笼照旧", "八仙过海各显神通", "姜太公钓鱼愿者上钩",
    "芝麻开花节节高", "飞蛾扑火自取灭亡", "猫哭耗子假慈悲",
    "黄鼠狼给鸡拜年没安好心", "鸡蛋里挑骨头", "骑驴看唱本走着瞧",
    "十五个吊桶打水七上八下", "打破砂锅问到底", "不到黄河心不死",
    "初生牛犊不怕虎", "宰相肚里能撑船", "狗咬吕洞宾不识好人心",
    "人心不足蛇吞象", "当局者迷旁观者清", "解铃还须系铃人",
    "此地无银三百两", "塞翁失马焉知非福", "亡羊补牢为时不晚",
    "一不做二不休", "一箭双雕", "一石二鸟", "东边日出西边雨",
]

added = 0
skipped = []
with open(CLASSICS, "a", encoding="utf-8") as out:
    for p in NEW:
        c = phrase_to_code(p)
        if c and len(c) == 4:
            out.write(c + " " + p + "\n")
            added += 1
        else:
            skipped.append(p)

# 去重（保留已有）
seen = set()
lines = []
for line in open(CLASSICS, encoding="utf-8"):
    parts = line.split()
    if len(parts) == 2 and parts[0] not in seen:
        seen.add(parts[0])
        lines.append(line)
with open(CLASSICS, "w", encoding="utf-8") as out:
    out.writelines(lines)

print("新增 %d 条经典语料（跳过 %d 条缺字）" % (added, len(skipped)))
if skipped:
    print("跳过:", " / ".join(skipped[:8]))
print("wubi86_classics.txt 总行数:", len(lines))
# 抽查验证
print("\n抽查（86 码应能对上）：")
import random
sample = random.sample(lines, min(5, len(lines)))
for l in sample:
    print(" ", l.strip())
