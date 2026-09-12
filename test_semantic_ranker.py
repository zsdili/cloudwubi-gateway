# -*- coding: utf-8 -*-
"""
test_semantic_ranker.py - 语义排序引擎单元测试

用法：
    python3 test_semantic_ranker.py
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from semantic_ranker import SemanticRanker


def test_high_freq_first():
    """高频词组应排到噪声组合前面"""
    ranker = SemanticRanker()
    ranker.feed_corpus(["你好", "人民", "中国", "世界"])

    candidates = [
        {"phrase": "人我好", "chars": [1, 2, 3], "code": "wqvb", "type": "word3"},
        {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
    ]
    ranked = ranker.rank(candidates)
    assert ranked[0]["phrase"] == "你好", f"期望你好在前，实际: {ranked[0]['phrase']}"
    print("✅ test_high_freq_first 通过")


def test_user_learning():
    """用户行为学习应能改变排序（越用越准）"""
    ranker = SemanticRanker()
    ranker.feed_corpus(["你好", "人民"])
    ranker.learn_selection("人我好", 10)

    candidates = [
        {"phrase": "人我好", "chars": [1, 2, 3], "code": "wqvb", "type": "word3"},
        {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
    ]
    ranked = ranker.rank(candidates)
    assert ranked[0]["phrase"] == "人我好", f"用户常用词应前置，实际: {ranked[0]['phrase']}"
    print("✅ test_user_learning 通过")


def test_char_weight():
    """单字候选应按常用度排序"""
    ranker = SemanticRanker()
    candidates = [
        {"phrase": "工", "chars": [1], "code": "a", "type": "char"},
        {"phrase": "经", "chars": [2], "code": "x", "type": "char"},
    ]
    ranked = ranker.rank(candidates)
    # 工(92) vs 经(84)，工应在前面
    assert ranked[0]["phrase"] == "工", f"工应在前，实际: {ranked[0]['phrase']}"
    print("✅ test_char_weight 通过")


def test_learning_persist():
    """用户行为应持久化到文件"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        ranker1 = SemanticRanker(user_data_path=path)
        ranker1.learn_selection("你好", 5)

        # 重新加载应能看到学习结果
        ranker2 = SemanticRanker(user_data_path=path)
        candidates = [
            {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
            {"phrase": "其他", "chars": [3, 4], "code": "xxxx", "type": "word2"},
        ]
        ranked = ranker2.rank(candidates)
        assert ranked[0]["phrase"] == "你好"
        print("✅ test_learning_persist 通过")
    finally:
        os.unlink(path)


def test_empty_input():
    """空候选应安全返回"""
    ranker = SemanticRanker()
    assert ranker.rank([]) == []
    assert ranker.rank(None) is None
    print("✅ test_empty_input 通过")


if __name__ == "__main__":
    test_high_freq_first()
    test_user_learning()
    test_char_weight()
    test_learning_persist()
    test_empty_input()
    print("\n✅ 语义排序引擎全部单元测试通过")
