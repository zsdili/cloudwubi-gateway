# -*- coding: utf-8 -*-
"""
test_layered_rank.py - 分层智能排序规则专项测试

验证用户固化的排序规则：
  1. 1码：高频单字优先（一级简码）
  2. 2码：先高频单字 → 再二字词
  3. MRU：上次选中的字/词优先置顶
  4. 3码：提示第4码的高频词组（前瞻预测）
  5. 热词：当代流行词（云计算/算力/人工智能）权重生效
  6. 词频：高频词组优先于噪声组合

用法：
    python3 test_layered_rank.py
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from semantic_ranker import SemanticRanker


def test_one_char_first():
    """1码：高频单字优先（一级简码）"""
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "经", "chars": [0x7ECF], "code": "x", "type": "char"},
        {"phrase": "一", "chars": [0x4E00], "code": "g", "type": "char"},
        {"phrase": "工", "chars": [0x5DE5], "code": "a", "type": "char"},
    ]
    ranked = ranker.rank(candidates, code_len=1)
    assert ranked[0]["phrase"] == "一", f"1码一级简码'一'应最前, 实际: {ranked[0]['phrase']}"
    print("✅ test_one_char_first 通过")


def test_two_char_then_phrase():
    """2码：先高频单字 → 再二字词"""
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "工作", "chars": [1, 2], "code": "aa", "type": "word2"},
        {"phrase": "工", "chars": [0x5DE5], "code": "a", "type": "char"},
    ]
    ranked = ranker.rank(candidates, code_len=2)
    # 单字（+25 分层分）应排在高频词（+12 分层分）前面
    assert ranked[0]["phrase"] == "工", f"2码时单字应优先, 实际: {ranked[0]['phrase']}"
    print("✅ test_two_char_then_phrase 通过")


def test_mru_priority():
    """MRU：上次选中的字/词优先置顶"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        ranker = SemanticRanker(user_data_path=path)
        ranker.learn_selection("人我好")  # 用户上次选了噪声词
        candidates = [
            {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
            {"phrase": "人我好", "chars": [1, 2, 3], "code": "wqvb", "type": "word3"},
        ]
        ranked = ranker.rank(candidates, code_len=4)
        assert ranked[0]["phrase"] == "人我好", f"MRU应置顶, 实际: {ranked[0]['phrase']}"
        print("✅ test_mru_priority 通过")
    finally:
        os.unlink(path)


def test_trend_words():
    """热词：当代流行词权重生效（云计算/人工智能）"""
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "云计算", "chars": [1, 2, 3], "code": "fyth", "type": "word3"},
        {"phrase": "地言处", "chars": [4, 5, 6], "code": "fyth", "type": "word3"},
    ]
    ranked = ranker.rank(candidates, code_len=4)
    assert ranked[0]["phrase"] == "云计算", f"热词'云计算'应优先, 实际: {ranked[0]['phrase']}"
    print("✅ test_trend_words 通过")


def test_freq_priority():
    """词频：高频词组优先于噪声组合"""
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "人我好", "chars": [1, 2, 3], "code": "wqvb", "type": "word3"},
        {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
    ]
    ranked = ranker.rank(candidates, code_len=4)
    assert ranked[0]["phrase"] == "你好", f"高频词'你好'应优先, 实际: {ranked[0]['phrase']}"
    print("✅ test_freq_priority 通过")


def test_prediction_3code():
    """3码：预测第4码的高频词组（index.py 集成验证）"""
    # 集成测试在网关层做，这里验证引擎不崩溃 + 热词可被预测
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "云", "chars": [0x4E91], "code": "fcu", "type": "char"},
        {"phrase": "人工智能", "chars": [1, 2, 3, 4], "code": "watc", "type": "prediction"},
    ]
    ranked = ranker.rank(candidates, code_len=3)
    assert ranked[0]["phrase"] == "人工智能", f"3码预测词应优先, 实际: {ranked[0]['phrase']}"
    print("✅ test_prediction_3code 通过")


if __name__ == "__main__":
    test_one_char_first()
    test_two_char_then_phrase()
    test_mru_priority()
    test_trend_words()
    test_freq_priority()
    test_prediction_3code()
    print("\n✅ 分层智能排序全部专项测试通过")
