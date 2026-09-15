#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_codes.py - 五笔规则随机验证（用户固化要求：每次规则验证 ≥50 次随机）
======================================================================
1. 从词组库随机抽取 ≥50 条词组
2. 用 86 全码规则（phrase_to_code）计算编码
3. 与词库编码比对：命中=规则正确；不一致=报告并修正（回归 86 官方规则）
4. 回归基准：jidian 权威词组库（官方 86 编码）
用法：python3 verify_codes.py [抽样数]（默认 60）
"""
import sys, random, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phrase_engine import PhraseEngine


def load_dict():
    d = {}
    for line in open("wubi86_basic.txt", encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 2:
            continue
        for w in p[1:]:
            if len(w) == 1:
                d.setdefault(p[0], []).append(ord(w))
    return d


def load_phrases():
    pd = {}
    for line in open("wubi86_phrases.txt", encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = line.split()
        if len(p) < 2:
            continue
        pd.setdefault(p[0], []).extend(p[1:])
    return pd


SIMPLE1 = {"g":"一","f":"地","d":"在","s":"要","a":"工","h":"上","j":"是","k":"中","l":"国",
            "m":"同","t":"和","r":"的","e":"有","w":"人","q":"我","y":"主","u":"产","i":"不",
            "o":"为","p":"这","n":"民","b":"了","v":"发","c":"以","x":"经"}
# 键名字（25 键根字根：4 码重复键名）
KEYNAMES = {"g":"王","f":"土","d":"大","s":"木","a":"工","h":"目","j":"日","k":"口","l":"田",
            "m":"山","t":"禾","r":"白","e":"月","w":"人","q":"金","y":"言","u":"立","i":"水",
            "o":"火","p":"之","n":"已","b":"子","v":"女","c":"又","x":"纟"}


def verify_simple1(d):
    """25 键一级简码验证（打 X 必须出现 X 的一级简码字且在最前）"""
    bad = []
    for k, expect in SIMPLE1.items():
        chars = [chr(x) for x in d.get(k, [])]
        if expect not in chars:
            bad.append((k, expect, chars[:3]))
        elif chars and chars[0] != expect:
            bad.append((k, expect, chars[:3]))
    return bad


def verify_keynames(d):
    """25 键键名字验证（4 码重复键名可打：gggg 王、rrrr 白……）"""
    bad = []
    for k, expect in KEYNAMES.items():
        chars = [chr(x) for x in d.get(k * 4, [])]
        if expect not in chars:
            bad.append((k * 4, expect, chars[:3]))
    return bad


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    if n < 50:
        print("⚠ 用户固化要求：随机验证 ≥50 次，已强制使用 60")
        n = 60
    d = load_dict()
    # ① 25 键一级简码验证（50 项内必含）
    bad1 = verify_simple1(d)
    print(f"一级简码验证 25 键：通过 {25 - len(bad1)}，异常 {len(bad1)}")
    for k, exp, got in bad1:
        print(f"  ✗ {k} 应出「{exp}」最前，实际 {got}")
    # ② 25 键键名字验证（4 码重复键名）
    bad2 = verify_keynames(d)
    print(f"键名字验证 25 键：通过 {25 - len(bad2)}，异常 {len(bad2)}")
    for k, exp, got in bad2:
        print(f"  ✗ {k} 应含「{exp}」，实际 {got}")
    pd = load_phrases()
    e = PhraseEngine(d, pd)
    word_codes = {}
    for c, pl in pd.items():
        for w in pl:
            word_codes.setdefault(w, set()).add(c)
    items = list(word_codes.items())
    random.seed(42)
    sample = random.sample(items, min(n, len(items)))
    match = 0
    mismatch = []
    for w, codes in sample:
        calc = e.phrase_to_code(w)
        if calc and calc in codes:
            match += 1
        else:
            mismatch.append((w, sorted(codes)[:3], calc))
    print(f"随机验证 {len(sample)} 条：全码规则命中 {match}，不一致 {len(mismatch)}")
    for w, lib, calc in mismatch:
        print(f"  ✗ {w}: 词库={lib} 全码计算={calc}（需回归 86 官方规则修正）")
    if mismatch or bad1 or bad2:
        print("❌ 未通过——请修正后重跑（词组全码/一级简码/键名字 任一异常即失败）")
        sys.exit(1)
    print("✅ 通过：全码规则、一级简码、键名字 与权威 86 规则 100% 一致")


if __name__ == "__main__":
    main()
