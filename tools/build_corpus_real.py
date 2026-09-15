#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
"""真实语料增强版语料生成器（可复现资产）
= 场景语料（词表保护）+ ChnSentiCorp 真实评论语料（MIT/公开数据）
→ /tmp/corpus_tok.txt（词级，供 n-gram 映射表 + 模型训练）
"""
import csv, random, re
import jieba
from build_corpus import PROTECT, scenes, tokenize, build

def add_real(lines, csv_path='/tmp/ChnSentiCorp_htl_all.csv', max_rows=7000):
    n = 0
    with open(csv_path, encoding='utf-8') as f:
        for row in csv.reader(f):
            if n == 0: n += 1; continue  # header
            if len(row) < 2 or n > max_rows: break
            txt = row[1].strip()
            if len(txt) < 8: n += 1; continue
            # 清理引号等
            txt = txt.replace('""', '"')
            lines.append(txt)
            n += 1
    return lines

def add_waimai(lines, csv_path='/tmp/waimai_10k.csv', max_rows=10000):
    """v0.6.2：外卖评论语料（口语化，贴近日常输入场景）"""
    n = 0
    with open(csv_path, encoding='utf-8') as f:
        for row in csv.reader(f):
            if n == 0: n += 1; continue
            if len(row) < 2 or n > max_rows: break
            txt = row[1].strip()
            if len(txt) < 6: n += 1; continue
            lines.append(txt)
            n += 1
    return lines

def main():
    lines = build(6000)
    lines = add_real(lines)
    lines = add_waimai(lines)
    with open('/tmp/corpus_tok.txt', 'w', encoding='utf-8') as f:
        for ln in lines:
            f.write(" ".join(tokenize(ln)) + "\n")
    # 字级
    def chars(tok):
        return list(tok) if re.match(r'^[\u4e00-\u9fff]+$', tok) else [tok]
    with open('/tmp/corpus_char.txt', 'w', encoding='utf-8') as f:
        for ln in lines:
            cs = []
            for t in tokenize(ln): cs.extend(chars(t))
            f.write(" ".join(cs) + "\n")
    print("✅ 真实语料增强:", len(lines), "行")

if __name__ == '__main__':
    main()
