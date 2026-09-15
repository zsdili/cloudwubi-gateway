#!/usr/bin/env python3
"""云五笔联想语料生成器（可复现资产）
1. 聚焦联想场景语料（词表保护：专有词/场景词整 token）
2. 输出 /tmp/corpus_tok.txt（词级）+ /tmp/corpus_char.txt（字级，供 n-gram 训练）
"""
import random, re
import jieba

PROTECT = ["钟总","早上好","朋友们","辛苦了","前进","方向","道路","号角","浪潮","前进路上",
           "想去医院","生病了","看医生","工作","学习","奋斗","合作","共赢","推进",
           "天气","多云","下雨","晴朗","办法","没关系","不需要","不出来","不知道",
           "谢谢","不客气","加油","努力","为什么","怎么办","去哪里"]
scenes = [
    (["前进","努力前进","向前进","大步前进"], ["方向","道路","号角","浪潮","吧","前进路上"]),
    (["想","我在想","心里想","正在想"], ["你","办法","一下","问题"]),
    (["今天生病了","今天不舒服","我生病了","身体不舒服"], ["想去医院","去医院","看医生","请假","休息"]),
    (["早上好","早安","大家早上好"], ["钟总","大家","朋友们","新的一天","美好的一天"]),
    (["辛苦了","大家辛苦了","钟总辛苦了"], ["钟总","大家","你","辛苦了"]),
    (["吃饭","去吃饭","吃"], ["饭","早餐","午饭","东西","食堂"]),
    (["工作","努力工作","认真工作"], ["顺利","加油","辛苦","完成"]),
    (["学习","努力学习","认真学习"], ["进步","知识","向上","奋斗"]),
    (["合作","真诚合作","合作愉快"], ["共赢","伙伴","愉快","推进"]),
    (["天气","今天天气","看天气"], ["很好","晴朗","下雨","多云"]),
    (["谢谢","谢谢你","感谢"], ["你","大家","帮忙","支持"]),
    (["加油","继续加油","一起加油"], ["努力","奋斗","吧","坚持"]),
]
def build(n=6000, seed=42):
    random.seed(seed)
    lines = []
    for _ in range(n):
        pre, post = random.choice(scenes)
        pre = random.choice(pre); w = random.choice(post)
        tmpl = random.choice(["{pre}{w}", "{pre}，{w}", "{pre}就是{w}", "{pre}要{w}", "{pre}，{w}。", "他说{pre}{w}", "{pre}{w}很重要"])
        lines.append(tmpl.format(pre=pre, w=w))
    generic = ["我知道了","没关系","不需要","不出来","不知道","谢谢你","不客气","有什么问题","怎么解决",
               "怎么办","去哪里","为什么","干什么","中国人民","认真听讲","前进方向","科学原理","合理布局","积极推进"]
    for g in generic:
        for _ in range(300): lines.append(g)
    return lines

def tokenize(s):
    out, i, n = [], 0, len(s)
    while i < n:
        hit = None
        for p in sorted(PROTECT, key=len, reverse=True):
            if s.startswith(p, i): hit = p; break
        if hit: out.append(hit); i += len(hit)
        else:
            j = i + 1
            while j <= n:
                if any(s.startswith(p, j-1) for p in PROTECT): break
                j += 1
            seg = s[i:j-1]
            if seg: out.extend(jieba.cut(seg))
            i = j - 1
    return out

def main():
    lines = build()
    with open('/tmp/corpus_tok.txt', 'w') as f:
        for ln in lines:
            f.write(" ".join(tokenize(ln)) + "\n")
    # 字级语料
    def chars(tok):
        return list(tok) if re.match(r'^[\u4e00-\u9fff]+$', tok) else [tok]
    with open('/tmp/corpus_char.txt', 'w') as f:
        for ln in lines:
            cs = []
            for t in tokenize(ln): cs.extend(chars(t))
            f.write(" ".join(cs) + "\n")
    print("✅ 语料生成:", len(lines), "行")

if __name__ == '__main__':
    main()
