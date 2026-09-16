#!/usr/bin/env python3
"""云五笔词库清洗（v0.7.16）：去除所有词库的非简体字（繁体）及其他噪音

用户反馈：打 yngk 候选出现"詞"（繁体）——词库含繁体字污染候选。
策略：opencc 繁→简，词含繁体（词 != 简转结果）→ 整词删除；同时过滤非汉字/异常词。
作用于：全部 wubi86_*.txt / wubi86_*.json / category_words*.json。
"""
import json, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    from opencc import OpenCC
    CC = OpenCC('t2s')
    HAVE_OPENCC = True
except Exception:
    CC = None
    HAVE_OPENCC = False

HAN = re.compile(r'^[\u4e00-\u9fff]+$')
# 简体常用字范围（GB2312 一级+二级，6763 字；超出=生僻字/繁体特殊字符 → 视作噪音可删）
GB2312 = None
def load_gb2312():
    global GB2312
    if GB2312 is not None:
        return GB2312
    chars = set()
    try:
        for cp in range(0x4E00, 0x9FFF):
            try:
                ch = chr(cp)
                ch.encode('gb2312')
                chars.add(ch)
            except Exception:
                pass
    except Exception:
        pass
    GB2312 = chars
    return chars

def is_clean_word(w):
    """词合格：全汉字 + 无繁体 + GB2312 简体范围"""
    if not HAN.match(w):
        return False
    if HAVE_OPENCC:
        if CC.convert(w) != w:
            return False  # 含繁体
    # GB2312 范围检查（生僻字过滤）
    gb = load_gb2312()
    if not all(c in gb for c in w):
        return False
    return True

def clean_line_words(words):
    return [w for w in words if is_clean_word(w)]

def process_text_file(fn):
    """每行：码 词...；清洗后仅保留合格词；无词的行删除"""
    path = os.path.join(BASE, fn)
    if not os.path.exists(path):
        return 0, 0
    out_lines, removed = [], 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                out_lines.append(line)
                continue
            parts = line.split()
            if len(parts) < 2:
                out_lines.append(line)
                continue
            code, words = parts[0], parts[1:]
            good = clean_line_words(words)
            removed += len(words) - len(good)
            if good:
                out_lines.append(code + ' ' + ' '.join(good))
            # 无词行删除
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out_lines) + ('\n' if out_lines else ''))
    return removed, len(out_lines)

def process_json_file(fn):
    path = os.path.join(BASE, fn)
    if not os.path.exists(path):
        return 0
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print(f"  !! {fn} 解析失败: {e}")
        return 0
    removed = 0
    if isinstance(data, dict):
        for k in list(data.keys()):
            v = data[k]
            if isinstance(v, list):
                good = [w for w in v if isinstance(w, str) and is_clean_word(w)]
                removed += len(v) - len(good)
                data[k] = good
            elif isinstance(v, str) and not is_clean_word(v):
                removed += 1
                del data[k]
    elif isinstance(data, list):
        good = [w for w in data if isinstance(w, str) and is_clean_word(w)]
        removed += len(data) - len(good)
        data = good
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=None, separators=(',', ':'))
    return removed

def main():
    print(f"opencc 可用: {HAVE_OPENCC}")
    total_removed = 0
    txt_files = ["wubi86_recalc.txt", "wubi86_report.txt", "wubi86_phrases.txt", "wubi86_daily.txt",
                 "wubi86_classics.txt", "wubi86_geo.txt", "wubi86_life.txt", "wubi86_mil.txt", "wubi86_poem.txt",
                 "wubi86_basic.txt"]
    for fn in txt_files:
        r, lines = process_text_file(fn)
        total_removed += r
        print(f"  {fn}: 删除 {r} 词条词，剩余 {lines} 行")
    json_files = [f for f in os.listdir(BASE) if f.startswith("wubi86_") and f.endswith(".json")] + \
                 [f for f in os.listdir(BASE) if f.startswith("category_words") and f.endswith(".json")]
    for fn in sorted(set(json_files)):
        r = process_json_file(fn)
        total_removed += r
        print(f"  {fn}: 删除 {r}")
    print(f"\n总计删除 {total_removed} 个非简体/噪音词条")

if __name__ == "__main__":
    main()
