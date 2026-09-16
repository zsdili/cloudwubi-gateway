#!/usr/bin/env python3
"""标准 86 五笔词组编码重算器（v0.7.14 治本）

问题：词库大量词组用"一级简码拼码"等错误编码（如 不要=is，应为 gisv），
      用户按标准全码规则打不出 → "无数4码词组出不来"。

方案：按 86 标准规则用单字全码重算全部词组编码：
  2字词 = 首字前2码 + 次字前2码
  3字词 = 首字前1码 + 次字前1码 + 三字前2码
  4字词 = 各字前1码
  5+字  = 前3字各1码 + 末字1码
缺码字（单字表未收录）的词保留原编码兜底。

输出：wubi86_recalc.txt（格式：编码 词...），并入部署包由 load_phrase_dict 优先加载。
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
CODE_RE = re.compile(r"^[a-z]{1,4}$")

def load_char_full():
    """字 -> 全码（取该字所有码中最长者；同长取后出现的——Rime 表按频率降序，长码在后）"""
    char_map = {}
    with open(os.path.join(BASE, "wubi86_basic.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2 or not CODE_RE.match(parts[0]):
                continue
            code = parts[0]
            for ch in parts[1:]:
                if len(ch) != 1:
                    continue
                cur = char_map.get(ch)
                if cur is None or len(code) > len(cur):
                    char_map[ch] = code
                elif len(code) == len(cur) and code != cur:
                    # 同长多码（罕见）取后出现的
                    char_map[ch] = code
    return char_map

def collect_words():
    """收集全部词组（码 -> [词]）"""
    words = {}
    text_files = ["wubi86_phrases.txt", "wubi86_daily.txt", "wubi86_classics.txt",
                  "wubi86_geo.txt", "wubi86_life.txt", "wubi86_mil.txt", "wubi86_poem.txt"]
    for fn in text_files:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2 or not CODE_RE.match(parts[0]):
                    continue
                for w in parts[1:]:
                    if 2 <= len(w) <= 12 and re.match(r"^[\u4e00-\u9fff]+$", w):
                        words.setdefault(w, set()).add(parts[0])
    # JSON 词库（{码: [词]}）
    for fn in sorted(os.listdir(BASE)):
        if fn.startswith("wubi86_") and fn.endswith(".json"):
            try:
                data = json.load(open(os.path.join(BASE, fn), encoding="utf-8"))
            except Exception:
                continue
            for c, ws in data.items():
                if isinstance(ws, list):
                    for w in ws:
                        if isinstance(w, str) and 2 <= len(w) <= 12:
                            words.setdefault(w, set()).add(c)
    return words

def recalc_code(word, char_map):
    """86 标准词组编码；返回 None 表示缺码"""
    codes = [char_map.get(ch) for ch in word]
    if any(c is None for c in codes):
        return None
    n = len(word)
    if n == 2:
        return codes[0][:2] + codes[1][:2]
    if n == 3:
        return codes[0][:1] + codes[1][:1] + codes[2][:2]
    if n == 4:
        return codes[0][:1] + codes[1][:1] + codes[2][:1] + codes[3][:1]
    return codes[0][:1] + codes[1][:1] + codes[2][:1] + codes[-1][:1]

def main():
    char_map = load_char_full()
    print(f"单字全码表: {len(char_map)} 字")
    words = collect_words()
    print(f"词组总数: {len(words)}")
    out = {}
    no_code = []
    for w, old_codes in words.items():
        c = recalc_code(w, char_map)
        if c is None:
            no_code.append(w)
            # 保留原编码兜底
            for oc in old_codes:
                out.setdefault(oc, []).append(w)
        else:
            out.setdefault(c, []).append(w)
    # 去重写文件
    lines = []
    for c in sorted(out.keys()):
        ws = sorted(set(out[c]))
        lines.append(c + " " + " ".join(ws))
    outp = os.path.join(BASE, "wubi86_recalc.txt")
    with open(outp, "w", encoding="utf-8") as f:
        f.write("# CloudWubi 标准86词组编码重算表（v0.7.14 生成，替代简码拼码错误编码）\n")
        f.write("\n".join(lines))
    print(f"重算输出: {len(out)} 码")
    print(f"缺码保留原编码: {len(no_code)} 词（前10: {no_code[:10]}）")
    # 验证关键词
    for w, expect in [("不要", "gisv"), ("可以", "skny"), ("知道", "tdut"),
                      ("前进", "uefj"), ("反馈", "rcqn"), ("国庆节", "lyab"),
                      ("一点", "gghk"), ("什么", "wftc"), ("名目", "qkhh"),
                      ("没办法", "ilif"), ("中国人民", "klwn"), ("操作系统", "rwtx"),
                      ("状态栏", "udsu"), ("为什么", "ywtc"), ("晚上好", "jhvb")]:
        got = recalc_code(w, char_map)
        mark = "✓" if got == expect else "✗"
        print(f"  {mark} {w}: {got} (期望 {expect})")

if __name__ == "__main__":
    main()
