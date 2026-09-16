#!/usr/bin/env python3
"""v0.5.75 全语料训练：①逗号句对（宋词/歇后语/成语例句/毛选/兵法/论语/道德经/口语评论）
②字级 2-gram + 3-gram 顺承表（匹配云端「末尾 3→1 字子串」查询）
输出：comma_pairs.json + ngram_link.json（剪枝控体积，SCF 128MB 内存约束）
"""
import json, re, os, csv
from collections import Counter, defaultdict

STOP_CH = set("，。！？、；：""''（）《》【】…—· \t\n\r")
KEEP1 = set("你我他她它们吧吗啊呢呀哦")

def clean(t):
    if not t: return ""
    t = re.sub(r'[^\u4e00-\u9fff，。！？、；：…—a-zA-Z0-9]', '', t)
    return t

texts = []      # 自然文本（字级训练 + 逗号对）
word_lines = [] # 已分词行（corpus_tok 词级 bigram）

def add_text(t):
    t = clean(t)
    if len(t) >= 4:
        texts.append(t)

# 1. 主分词语料（词级直接用，字级拼接）
if os.path.exists('corpus/corpus_tok.txt'):
    for line in open('corpus/corpus_tok.txt', encoding='utf-8'):
        line = line.strip()
        if line:
            word_lines.append(line)
            add_text(''.join(line.split()))

# 2. 酒店/外卖评论
for f in ('corpus/ChnSentiCorp_htl_all.csv', 'corpus/waimai_10k.csv'):
    if not os.path.exists(f):
        continue
    try:
        for row in csv.reader(open(f, encoding='utf-8')):
            for cell in row:
                if cell and any('\u4e00' <= ch <= '\u9fff' for ch in cell) and len(cell) >= 6:
                    add_text(cell)
    except Exception:
        pass

# 3. 歇后语（riddle→answer 天然逗号句对）
if os.path.exists('/tmp/chinese-xinhua/data/xiehouyu.json'):
    for it in json.load(open('/tmp/chinese-xinhua/data/xiehouyu.json')):
        add_text((it.get('riddle') or '') + '，' + (it.get('answer') or ''))

# 4. 成语例句
if os.path.exists('/tmp/chinese-xinhua/data/idiom.json'):
    for it in json.load(open('/tmp/chinese-xinhua/data/idiom.json')):
        ex = it.get('example') or ''
        if len(ex) >= 8:
            add_text(ex)
        w = it.get('word') or ''
        if len(w) >= 3:
            add_text(w)

# 5. 毛选 / 孙子兵法
for d in ('corpus/maoxuan', 'corpus/sunzi'):
    if os.path.isdir(d):
        for f in os.listdir(d):
            try:
                add_text(open(os.path.join(d, f), encoding='utf-8').read())
            except Exception:
                pass

# 6. 论语
if os.path.exists('corpus/lunyu.json'):
    for c in json.load(open('corpus/lunyu.json')):
        for p in c.get('paragraphs', []):
            add_text(p)

# 7. 道德经
if os.path.exists('corpus/daodejing.md'):
    add_text(open('corpus/daodejing.md', encoding='utf-8').read())

# ═══ A. 逗号句对（前句→后句，歇后语/对仗/连贯句）═══
pairs = {}
xiehou_pairs = {}   # 歇后语对全量保留（用户核心需求：打逗号联想下半句）
def add_pair(pairs_dict, a, b):
    if len(a) >= 3 and len(b) >= 3 and a != b:
        if a not in pairs_dict:
            pairs_dict[a] = []
        if b not in pairs_dict[a]:
            pairs_dict[a].append(b)

# A0. 歇后语对（riddle→answer，全量优先）
if os.path.exists('/tmp/chinese-xinhua/data/xiehouyu.json'):
    for it in json.load(open('/tmp/chinese-xinhua/data/xiehouyu.json')):
        r = clean(it.get('riddle') or '').strip('，、')
        a = clean(it.get('answer') or '').strip('，、')
        if r and a:
            add_pair(xiehou_pairs, r, a)
            for rp in re.split(r'[，、]', r):
                if len(rp) >= 3 and rp != a:
                    add_pair(xiehou_pairs, rp, a)

for t in texts:
    for seg in re.split(r'[。！？\n]+', t):
        seg = seg.strip('，,、；')
        parts = [p.strip('，、') for p in re.split(r'[，、]', seg) if len(p.strip('，、')) >= 3]
        for i in range(len(parts) - 1):
            add_pair(pairs, parts[i], parts[i + 1])

comma_out = {k: v[:3] for k, v in pairs.items() if v}
# 控体积：普通对键上限 4000（歇后语对不受限）
if len(comma_out) > 4000:
    ordered = sorted(comma_out.items(), key=lambda kv: -sum(len(x) for x in kv[1]))
    comma_out = dict(ordered[:4000])
# 合并：歇后语对优先（全量）+ 普通对（截断）
for k, v in xiehou_pairs.items():
    if k not in comma_out:
        comma_out[k] = v[:3]
    else:
        seen = set(comma_out[k])
        comma_out[k] += [x for x in v if x not in seen][:2]
print('逗号句对键:', len(comma_out), '| 歇后语对:', len(xiehou_pairs))

# ═══ B. 顺承表（词级 bigram + 字级 2/3-gram；键=前文，值=后续）═══
links = defaultdict(list)
cnt = Counter()

# B1. 词级 bigram：corpus_tok 分词行（词→后续词，联想候选为完整词）
for line in word_lines:
    toks = ['<s>'] + line.split() + ['</s>']
    for i in range(len(toks) - 1):
        a, b = toks[i], toks[i + 1]
        if a in ('<s>', '</s>') or b in ('<s>', '</s>') or b in STOP_CH:
            continue
        key = a if len(a) <= 3 else a[-2:]
        links[key].append((b, 1))
        cnt[key] += 1

# B2. 字级 2-gram：前1字 → 后1字
b2 = Counter()
for t in texts:
    ch = list(t)
    for i in range(len(ch) - 1):
        b2[(ch[i], ch[i + 1])] += 1
for (a, b), c in b2.items():
    if c < 2 or b in STOP_CH:
        continue
    if len(b) == 1 and b not in KEEP1:
        continue
    links[a].append((b, c))
    cnt[a] += c

# B3. 字级 3-gram：前2字 → 后1字
b3 = Counter()
for t in texts:
    ch = list(t)
    for i in range(len(ch) - 2):
        b3[(ch[i], ch[i + 1], ch[i + 2])] += 1
for (a, b, cc), c in b3.items():
    if c < 2 or cc in STOP_CH:
        continue
    if len(cc) == 1 and cc not in KEEP1:
        continue
    links[a + b].append((cc, c))
    cnt[a + b] += c

def topn(lst, n=5):
    d = {}
    for w, c in lst:
        d[w] = d.get(w, 0) + c
    return [w for w, _ in sorted(d.items(), key=lambda x: -x[1])[:n]]

ngram_out = {}
for k, v in links.items():
    if cnt[k] < 2:
        continue
    ngram_out[k] = topn(v)
# 控体积：键上限 60000（高频优先）
if len(ngram_out) > 60000:
    order = sorted(ngram_out.items(), key=lambda kv: -cnt[kv[0]])
    ngram_out = dict(order[:60000])
print('ngram 键:', len(ngram_out))

json.dump(comma_out, open('comma_pairs.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(ngram_out, open('ngram_link.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('comma_pairs.json:', os.path.getsize('comma_pairs.json'), 'B | ngram_link.json:', os.path.getsize('ngram_link.json'), 'B')

# 抽查
for k in ['床前明月光', '早上好', '前进', '做砖的坯子', '学而时习之', '只要功夫深', '竹篮打水']:
    print('逗号抽查', k, '→', comma_out.get(k, '(无)'))
for k in ['前进', '辛苦了', '想办法', '学习', '想', '的', '大', '认真']:
    print('ngram抽查', k, '→', ngram_out.get(k, '(无)'))
