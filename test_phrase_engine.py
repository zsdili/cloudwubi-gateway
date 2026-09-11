# -*- coding: utf-8 -*-
"""
test_phrase_engine.py - 构词引擎单元测试

用法：
    python3 -m pytest test_phrase_engine.py -v
    或直接 python3 test_phrase_engine.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from phrase_engine import PhraseEngine

# 测试码表
TEST_DICT = {
    "wq": [0x4F60],   # 你
    "vb": [0x597D],   # 好
    "w":  [0x4EBA],   # 人
    "n":  [0x6C11],   # 民
    "aw": [0x5171],   # 共
    "g":  [0x4E00],   # 一
    "gg": [0x4E16],   # 世
    "gjk": [0x754C],  # 界
}


def test_code_valid():
    eng = PhraseEngine(TEST_DICT)
    assert eng.code_valid("wq") is True
    assert eng.code_valid("gggg") is True
    assert eng.code_valid("z") is False
    assert eng.code_valid("") is False
    assert eng.code_valid("ggggg") is False


def test_single_char():
    eng = PhraseEngine(TEST_DICT)
    result = eng.build_phrases("wq")
    assert any(c["phrase"] == "你" for c in result)


def test_two_char_word():
    eng = PhraseEngine(TEST_DICT)
    result = eng.build_phrases("wqvb")
    assert any(c["phrase"] == "你好" for c in result)


def test_phrase_to_code():
    eng = PhraseEngine(TEST_DICT)
    assert eng.phrase_to_code("你好") == "wqvb"
    # 三字词：首+首+前2码（你=wq 首码w，好=vb）
    assert eng.phrase_to_code("你你好") == "wwvb"


def test_unknown_char():
    eng = PhraseEngine(TEST_DICT)
    assert eng.phrase_to_code("你X") is None  # X 不在码表


def test_invalid_input():
    eng = PhraseEngine(TEST_DICT)
    assert eng.build_phrases("zz") == []
    assert eng.build_phrases("") == []


def test_max_results():
    eng = PhraseEngine(TEST_DICT)
    # 四字词场景会产生较多结果，验证上限
    result = eng.build_phrases("gggg", max_results=10)
    assert len(result) <= 10


if __name__ == "__main__":
    test_code_valid()
    test_single_char()
    test_two_char_word()
    test_phrase_to_code()
    test_unknown_char()
    test_invalid_input()
    test_max_results()
    print("✅ 构词引擎全部单元测试通过")
