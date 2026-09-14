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


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    if n < 50:
        print("⚠ 用户固化要求：随机验证 ≥50 次，已强制使用 60")
        n = 60
    pd = load_phrases()
    e = PhraseEngine(load_dict(), pd)
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
    if mismatch:
        print("❌ 未通过——请修正 phrase_engine 或词组库后重跑")
        sys.exit(1)
    print("✅ 通过：全码规则与权威词库 100% 一致")


if __name__ == "__main__":
    main()
