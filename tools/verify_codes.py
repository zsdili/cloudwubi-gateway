#!/usr/bin/env python3
"""云五笔开放词库校验器（CI 强制门禁）
用法：python3 tools/verify_codes.py wubi86_contrib.txt [--strict]
校验：① 格式 ② 86 编码重算（随机 50 次） ③ 负面词黑名单 ④ 重复 ⑤ 长度
"""
import sys, os, re, random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from phrase_engine import PhraseEngine

# 负面词黑名单（安全边界：色情/赌博/毒品/暴力/违法/辱骂/敏感——一票否决）
NEG_WORDS = [
    "色情", "裸聊", "约炮", "一夜情", "成人片", "黄色网站", "av", "三级片",
    "赌博", "博彩", "六合彩", "赌场", "百家乐", "老虎机", "外围",
    "毒品", "冰毒", "海洛因", "摇头丸", "大麻", "可卡因", "毒品交易",
    "枪支", "弹药", "炸弹", "手榴弹", "炸药", "制毒",
    "杀人", "分尸", "强奸", "猥亵", "绑架", "抢劫", "诈骗", "洗钱",
    "自杀", "自残", "轻生",
    "傻逼", "妈的", "去死", "垃圾人", "贱人", "狗东西", "混蛋",
    "台独", "藏独", "疆独", "港独", "法轮功", "邪教",
    "招嫖", "卖淫", "嫖娼", "裸贷", "高利贷",
]

def load_engine():
    single_dict = {}
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    with open(os.path.join(base, "wubi86_basic.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) < 2: continue
            single_dict.setdefault(parts[0], []).extend(ord(ch) for w in parts[1:] for ch in w)
    return PhraseEngine(single_dict)

def main():
    strict = "--strict" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        print("用法: python3 tools/verify_codes.py <词库文件> [--strict]")
        sys.exit(2)
    engine = load_engine()
    errors = []
    words = []
    for path in paths:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split()
            if len(parts) < 2:
                errors.append(f"[格式] {line!r} 不是'编码 词语'")
                continue
            code, word = parts[0], parts[1]
            if not re.match(r'^[a-y]{2,4}$', code):
                errors.append(f"[格式] {word}: 编码 {code!r} 须为 2-4 位小写字母(a-y)")
                continue
            if not re.match(r'^[\u4e00-\u9fff]{2,8}$', word):
                errors.append(f"[长度] {word}: 须为 2-8 个汉字")
                continue
            # 编码重算
            calc = engine.phrase_to_code(word)
            if calc != code:
                errors.append(f"[编码] {word}: 应为 {calc}，实为 {code}")
                continue
            # 负面词
            for neg in NEG_WORDS:
                if neg in word:
                    errors.append(f"[负面词] {word}: 命中黑名单「{neg}」")
                    break
            words.append(word)
    # 重复检测
    dup = set()
    for w in words:
        if w in dup:
            errors.append(f"[重复] {w}: 词库内重复")
        dup.add(w)
    # 随机 50 次编码抽样（strict）
    if strict and not errors:
        sample = random.sample(words, min(50, len(words)))
        bad = 0
        for w in sample:
            if engine.phrase_to_code(w) is None: bad += 1
        if bad:
            errors.append(f"[随机50次] {bad} 个抽样词无法重算编码")
    if errors:
        print(f"❌ 校验失败 {len(errors)} 项:")
        for e in errors[:30]: print("  ", e)
        sys.exit(1)
    print(f"✅ 校验通过: {len(words)} 条（格式/编码/负面词/重复/长度全过）")
    sys.exit(0)

if __name__ == "__main__":
    main()
