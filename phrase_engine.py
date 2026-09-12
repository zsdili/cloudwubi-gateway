# -*- coding: utf-8 -*-
"""
phrase_engine.py - CloudWubi 五笔动态构词引擎（阶段2核心）
============================================================

原理（对标 26 键拼音的动态组词逻辑）：
  五笔词组**不需要预先存储**，只要掌握「单字编码」+「构词公式」，
  即可动态生成任意合法词组。

86 五笔构词公式（官方规则）：
  1. 二字词：第1字前2码 + 第2字前2码  （4码）
  2. 三字词：第1字首码 + 第2字首码 + 第3字前2码（4码）
  3. 四字及以上：第1/2/3/末字各取首码（4码）

示例：
  编码库有：你=wq, 好=vb, 中国=kl, 人=w, 民=n, 共=aw
  输入 "wqvb" -> 拆解为 你(wq) + 好(vb) -> 动态生成词组 "你好"
  输入 "wnwg" -> 拆解为 人(w) 民(n) 共(aw)... -> 组合生成

本引擎实现：
  1. 正向构词：输入 4 码编码 -> 查找可匹配的单字序列 -> 组合出词组
  2. 反向校验：给定词组 -> 按公式计算其五笔编码（用于规则库校验）
"""

import re
from functools import lru_cache

# 编码正则：1~4 位 a~y
CODE_RE = re.compile(r"^[a-y]{1,4}$")


class PhraseEngine:
    """五笔构词引擎（词库优先 + 动态构词兜底，阶段2/3升级版）"""

    def __init__(self, single_dict, phrase_dict=None):
        """
        single_dict: 单字编码字典
            { "编码": [Unicode码点, ...], ... }
        phrase_dict: 词组编码字典（词库层，可选）
            { "编码": [词组字符串, ...], ... }
            例如 { "wqvb": ["你好", ...], "kl": ["中国", ...], ... }
        """
        # 单字码表：编码 -> 汉字列表
        self.single_dict = single_dict
        # 词组码表：编码 -> 词组列表（词库层，行业标准做法）
        self.phrase_dict = phrase_dict or {}
        # 反向索引：汉字(码点) -> 编码（用于反向校验）
        self.char_to_code = {}
        self._build_reverse_index()

    def _build_reverse_index(self):
        """构建 汉字 -> 编码 反向索引。"""
        for code, chars in self.single_dict.items():
            for cp in chars:
                # 保留最短编码（一级简码优先）
                if cp not in self.char_to_code or len(code) < len(self.char_to_code[cp]):
                    self.char_to_code[cp] = code

    # ------------------------------------------------------------------
    # 正向构词：输入编码 -> 候选词组
    # ------------------------------------------------------------------
    def build_phrases(self, code: str, max_results: int = 10) -> list:
        """
        输入 1~4 码编码，生成候选词组。
        策略：词库优先（权威词组表） + 动态构词兜底（未收录词组时拼字）。

        返回 [{"phrase": "你好", "chars": [20320, 22909], "code": "wqvb", "type": "word2"}, ...]
        """
        code = code.lower().strip()
        if not CODE_RE.match(code):
            return []

        candidates = []
        used = set()

        # 场景0（新增）：词库优先 —— 查权威词组表
        if code in self.phrase_dict:
            for phrase in self.phrase_dict[code]:
                if phrase not in used:
                    candidates.append({
                        "phrase": phrase,
                        "chars": [ord(ch) for ch in phrase],
                        "code": code,
                        "type": "lexicon",  # 词库命中
                    })
                    used.add(phrase)

        # 场景1：直接命中单字（1~4码都可能）
        if code in self.single_dict:
            for cp in self.single_dict[code]:
                if chr(cp) not in used:
                    candidates.append({
                        "phrase": chr(cp),
                        "chars": [cp],
                        "code": code,
                        "type": "char",
                    })
                    used.add(chr(cp))

        # 场景2：二字词动态兜底（4码 = 前2码 + 后2码，仅当词库未命中时）
        if len(code) == 4 and not any(c["type"] == "lexicon" for c in candidates):
            first2 = code[0:2]
            last2 = code[2:4]
            if first2 in self.single_dict and last2 in self.single_dict:
                for cp1 in self.single_dict[first2][:3]:
                    for cp2 in self.single_dict[last2][:3]:
                        phrase = chr(cp1) + chr(cp2)
                        if phrase not in used:
                            candidates.append({
                                "phrase": phrase,
                                "chars": [cp1, cp2],
                                "code": code,
                                "type": "word2",
                            })
                            used.add(phrase)

        # 场景3：三字词动态兜底（词库未命中时才拼字）
        has_lex = any(c["type"] == "lexicon" for c in candidates)
        if len(code) == 4 and not has_lex:
            c1 = code[0:1]
            c2 = code[1:2]
            c3 = code[2:4]
            if c1 in self.single_dict and c2 in self.single_dict and c3 in self.single_dict:
                for cp1 in self.single_dict[c1][:2]:
                    for cp2 in self.single_dict[c2][:2]:
                        for cp3 in self.single_dict[c3][:2]:
                            phrase = chr(cp1) + chr(cp2) + chr(cp3)
                            if phrase not in used:
                                candidates.append({
                                    "phrase": phrase,
                                    "chars": [cp1, cp2, cp3],
                                    "code": code,
                                    "type": "word3",
                                })
                                used.add(phrase)

        # 场景4：四字词动态兜底（词库未命中时才拼字）
        if len(code) == 4 and not has_lex:
            c1 = code[0:1]
            c2 = code[1:2]
            c3 = code[2:3]
            c4 = code[3:4]
            if (c1 in self.single_dict and c2 in self.single_dict and
                    c3 in self.single_dict and c4 in self.single_dict):
                for cp1 in self.single_dict[c1][:1]:
                    for cp2 in self.single_dict[c2][:1]:
                        for cp3 in self.single_dict[c3][:1]:
                            for cp4 in self.single_dict[c4][:1]:
                                phrase = chr(cp1) + chr(cp2) + chr(cp3) + chr(cp4)
                                if phrase not in used:
                                    candidates.append({
                                        "phrase": phrase,
                                        "chars": [cp1, cp2, cp3, cp4],
                                        "code": code,
                                        "type": "word4",
                                    })
                                    used.add(phrase)

        # 限制返回数量（语义排序在阶段3接入）
        return candidates[:max_results]

    # ------------------------------------------------------------------
    # 反向校验：词组 -> 五笔编码（用于规则库CI校验）
    # ------------------------------------------------------------------
    def phrase_to_code(self, phrase: str):
        """
        根据构词公式，计算词组的五笔编码。
        返回编码字符串；若包含未知汉字返回 None。
        """
        chars = list(phrase)
        n = len(chars)
        if n == 0:
            return None

        codes = []
        for ch in chars:
            cp = ord(ch)
            if cp not in self.char_to_code:
                return None
            codes.append(self.char_to_code[cp])

        if n == 1:
            return codes[0]
        elif n == 2:
            # 二字词：前2码 + 后2码
            return (codes[0][0:2] + codes[1][0:2])
        elif n == 3:
            # 三字词：首 + 首 + 前2码
            return (codes[0][0:1] + codes[1][0:1] + codes[2][0:2])
        else:
            # 四字及以上：首+首+首+末首
            return (codes[0][0:1] + codes[1][0:1] + codes[2][0:1] + codes[-1][0:1])

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def code_valid(code: str) -> bool:
        return bool(CODE_RE.match(code))


# ------------------------------------------------------------------
# 便捷函数：供 index.py 调用
# ------------------------------------------------------------------
_engine = None


def get_engine(single_dict=None):
    """获取全局构词引擎实例（懒加载）。"""
    global _engine
    if _engine is None:
        _engine = PhraseEngine(single_dict or {})
    return _engine


def build_phrases(code: str, single_dict=None, max_results: int = 10) -> list:
    """便捷入口：输入编码 -> 候选词组列表。"""
    engine = get_engine(single_dict)
    return engine.build_phrases(code, max_results)


if __name__ == "__main__":
    # 本地自测
    test_dict = {
        "wq": [0x4F60],   # 你
        "vb": [0x597D],   # 好
        "w": [0x4EBA],    # 人
        "n": [0x6C11],    # 民
        "aw": [0x5171],   # 共
        "g": [0x4E00],    # 一
        "gg": [0x4E16],   # 世（简码示例）
        "gjk": [0x754C],  # 界
    }
    eng = PhraseEngine(test_dict)

    print("=== 测试1：二字词 wqvb (你好) ===")
    for c in eng.build_phrases("wqvb", 5):
        print(f"  {c['phrase']} ({c['type']})")

    print("=== 测试2：单字 wq (你) ===")
    for c in eng.build_phrases("wq", 5):
        print(f"  {c['phrase']} ({c['type']})")

    print("=== 测试3：三字词 wngjk? 用简化数据 ===")
    for c in eng.build_phrases("gngg", 5):
        print(f"  {c['phrase']} ({c['type']})")

    print("=== 测试4：反向校验 '你好' ===")
    print(f"  {eng.phrase_to_code('你好')} (期望 wqvb)")

    print("=== 测试5：反向校验 '人民' ===")
    print(f"  {eng.phrase_to_code('人民')} (期望 wnna 或类似)")
