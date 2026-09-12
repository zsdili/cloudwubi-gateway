# -*- coding: utf-8 -*-
"""
semantic_ranker.py - CloudWubi 语义排序引擎（阶段3核心）
=========================================================

解决问题：构词引擎机械组合会产生大量无意义候选（如"人我好"）。
本模块对候选词组做语义排序，让"高价值候选"排前面。

排序信号（三层，可插拔）：
  1. 词频权重（静态）：内置高频词组表 + 常用字权重，基础排序
  2. 用户行为权重（动态）：用户选中过的词组获得加分（云端持久化）
  3. 流畅度权重（统计）：基于 Bigram 共现概率，判断组合是否自然

设计原则：
  - 纯 Python 标准库，无重型依赖（保持云函数轻量）
  - 模块可插拔：每层排序信号可独立开启/关闭
  - 输入 = 构词引擎候选列表，输出 = 重排后的候选列表
"""

import json
import os
from collections import defaultdict

# ------------------------------------------------------------------
# 高频词组表（静态权重，来源：公开中文词频统计常用词）
# 格式：词组 -> 权重（越大越靠前）
# ------------------------------------------------------------------
DEFAULT_HIGH_FREQ = {
    "你好": 100,
    "人民": 95,
    "中国": 98,
    "世界": 90,
    "企业": 92,
    "工作": 88,
    "发展": 93,
    "经济": 85,
    "技术": 90,
    "创新": 89,
    "创业": 91,
    "投资": 87,
    "融资": 84,
    "数据": 88,
    "数字": 80,
    "云端": 82,
    "智能": 86,
    "未来": 83,
    "平台": 84,
    "服务": 85,
    "产品": 86,
    "项目": 84,
    "团队": 82,
    "资本": 80,
    "利润": 78,
    "增长": 82,
    "市场": 83,
    "营销": 75,
    "品牌": 78,
    "软件": 80,
    "硬件": 76,
    "网络": 78,
    "生态": 79,
    "客户": 80,
    "人力": 72,
    "智能": 86,
}

# 当代热词（与时俱进：云计算/算力/人工智能等，2020s 高频新词）
DEFAULT_TREND_WORDS = {
    "云计算": 95, "算力": 90, "云服务": 92, "人工智能": 98,
    "大模型": 96, "数字化": 90, "智能化": 89, "大数据": 92,
    "机器学习": 88, "深度学习": 86, "自然语言": 82, "算法": 88,
    "芯片": 85, "半导体": 84, "新能源": 86, "碳中和": 80,
    "物联网": 82, "区块链": 78, "元宇宙": 76, "自动驾驶": 80,
    "机器人": 84, "智能制造": 88, "工业互联网": 82, "数字经济": 90,
    "5G": 88, "6G": 84, "边缘计算": 82, "量子计算": 80,
    "AIGC": 92, "生成式AI": 90, "开源": 88, "去中心化": 82,
    "国产化": 80, "信创": 78, "赋能": 86, "落地": 82,
    "数智化": 88, "超级计算": 80, "数据中心": 84, "上云": 82,
}

# 常用单字权重（用于单字候选排序，如一级简码优先）
DEFAULT_CHAR_WEIGHT = {
    "一": 100, "地": 95, "在": 98, "要": 90, "工": 92,
    "上": 96, "是": 99, "中": 97, "国": 96, "同": 88,
    "和": 94, "的": 100, "有": 95, "人": 98, "我": 97,
    "主": 85, "产": 86, "不": 94, "为": 93, "这": 92,
    "民": 90, "了": 93, "发": 85, "以": 88, "经": 84,
    "你": 92, "好": 86, "世": 80, "界": 80,
}


class SemanticRanker:
    """语义排序引擎"""

    def __init__(self, high_freq=None, char_weight=None,
                 user_data_path=None, enable_fluency=True):
        self.high_freq = dict(DEFAULT_HIGH_FREQ)
        if high_freq:
            self.high_freq.update(high_freq)
        # 合并当代热词（与时俱进）
        self.high_freq.update(DEFAULT_TREND_WORDS)
        self.char_weight = dict(DEFAULT_CHAR_WEIGHT)
        if char_weight:
            self.char_weight.update(char_weight)
        self.enable_fluency = enable_fluency

        # 用户行为权重（动态学习）
        self.user_weight = defaultdict(int)
        self.user_data_path = user_data_path
        if user_data_path and os.path.exists(user_data_path):
            self._load_user_data()

        # MRU：最近选中的字/词（优先置顶，本次会话内 + 持久化）
        self.mru = []
        self.mru_path = (user_data_path or "").replace(".json", "_mru.json")
        if self.mru_path and os.path.exists(self.mru_path):
            self._load_mru()

        # Bigram 流畅度统计（动态构建）
        self.bigram_count = defaultdict(int)
        self.unigram_count = defaultdict(int)

    # ------------------------------------------------------------------
    # 用户行为学习
    # ------------------------------------------------------------------
    def _load_user_data(self):
        """加载用户行为权重（JSON: {词组: 次数}）。"""
        try:
            with open(self.user_data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for phrase, count in data.items():
                    self.user_weight[phrase] += int(count)
        except (IOError, ValueError):
            pass

    def learn_selection(self, phrase, count=1):
        """用户选中某个候选词组 -> 权重+1（云端持久化）。"""
        self.user_weight[phrase] += count
        if self.user_data_path:
            try:
                with open(self.user_data_path, "w", encoding="utf-8") as f:
                    json.dump(dict(self.user_weight), f, ensure_ascii=False)
            except IOError:
                pass
        # 同时记录 MRU（最近选中）
        self._remember(phrase)

    # ------------------------------------------------------------------
    # MRU：最近选中优先置顶
    # ------------------------------------------------------------------
    def _load_mru(self):
        """加载 MRU 列表（JSON: [词组, ...]，最近在前）。"""
        try:
            with open(self.mru_path, "r", encoding="utf-8") as f:
                self.mru = json.load(f)
        except (IOError, ValueError):
            self.mru = []

    def _remember(self, phrase):
        """记录最近选中的字/词（置顶，最多保留 50 条）。"""
        if phrase in self.mru:
            self.mru.remove(phrase)
        self.mru.insert(0, phrase)
        self.mru = self.mru[:50]
        if self.mru_path:
            try:
                with open(self.mru_path, "w", encoding="utf-8") as f:
                    json.dump(self.mru, f, ensure_ascii=False)
            except IOError:
                pass

    def _mru_rank(self, phrase):
        """MRU 排名（越小越靠前；未命中返回大值）。"""
        if phrase in self.mru:
            return self.mru.index(phrase)
        return 9999

    # ------------------------------------------------------------------
    # 流畅度统计（Bigram）
    # ------------------------------------------------------------------
    def feed_corpus(self, phrases):
        """用词组语料构建 Bigram 共现统计（可在启动时加载）。"""
        for phrase in phrases:
            chars = list(phrase)
            for i in range(len(chars) - 1):
                bigram = chars[i] + chars[i + 1]
                self.bigram_count[bigram] += 1
                self.unigram_count[chars[i]] += 1
            if chars:
                self.unigram_count[chars[-1]] += 1

    def _fluency_score(self, phrase):
        """计算词组流畅度（0~1）：Bigram 平均共现概率。"""
        chars = list(phrase)
        if len(chars) < 2:
            return 1.0
        total = 0.0
        valid = 0
        for i in range(len(chars) - 1):
            bigram = chars[i] + chars[i + 1]
            cnt = self.bigram_count.get(bigram, 0)
            uni = self.unigram_count.get(chars[i], 0)
            if uni > 0:
                total += cnt / uni
                valid += 1
        if valid == 0:
            # 无统计信息时给基础分（0.5），不惩罚未知组合
            return 0.5
        return total / valid

    # ------------------------------------------------------------------
    # 核心：综合排序（分层智能排序）
    # ------------------------------------------------------------------
    def rank(self, candidates, code_len=None):
        """
        对构词引擎候选列表排序（原地修改，返回重排后的列表）。
        code_len: 输入编码长度（1/2/3/4），用于分层排序规则。

        分层规则（科学+先进）：
          - MRU 置顶：上次选中的字/词永远最优先（用户习惯）
          - 1 码：高频单字优先（一级简码）
          - 2 码：先高频单字 → 再二字词组（简码字>词组）
          - 3 码：提示第 4 码的高频词组（三级简码字 + 词组预测）
          - 4 码：词库词组优先 → 单字
        """
        if not candidates:
            return candidates

        # 第一步：MRU 置顶（最高优先级，用户习惯记忆）
        mru_first = [c for c in candidates if c["phrase"] in self.mru]
        mru_first.sort(key=lambda c: self._mru_rank(c["phrase"]))
        rest = [c for c in candidates if c["phrase"] not in self.mru]

        # 第二步：分层门槛（科学编码规则，优先于词频）
        # 1码：单字>一切；2码：单字>词组；3码：单字+预测词组；4码：词库词组>单字
        clen = code_len or max((len(c.get("code", "")) for c in rest), default=0)
        layer = {}  # phrase -> 分层值（越小越优先）
        for cand in rest:
            phrase = cand["phrase"]
            if cand["type"] == "char":
                if clen == 1:
                    layer[phrase] = 0      # 1码：一级简码单字最优先
                elif clen == 2:
                    layer[phrase] = 0      # 2码：单字在词组前
                elif clen == 3:
                    layer[phrase] = 1      # 3码：三级简码字
                else:
                    layer[phrase] = 2      # 4码：单字殿后
            elif cand["type"] in ("lexicon", "prediction"):
                if clen == 2:
                    layer[phrase] = 1      # 2码：词组在单字后
                elif clen == 3:
                    layer[phrase] = 0      # 3码：预测词组最优先（提示第4码）
                else:
                    layer[phrase] = 1      # 4码：词库词组优先于单字
            else:  # 动态拼接词（word2/3/4）
                layer[phrase] = 3          # 动态兜底词排最后（避免噪声置顶）

        for cand in rest:
            phrase = cand["phrase"]
            score = 0.0

            # 信号0：分层门槛（主导信号，远大于词频）
            score += (4 - layer[phrase]) * 100.0

            # 信号1：词频权重（含当代热词）
            freq = self.high_freq.get(phrase, 0)
            score += freq * 0.5

            # 信号2：用户行为权重（用户选择是最高置信信号）
            user = self.user_weight.get(phrase, 0)
            score += user * 30.0  # 用户行为权重远高于静态词频（实现"越用越准"）

            # 信号3：单字权重（单字候选）
            if cand["type"] == "char":
                score += self.char_weight.get(phrase, 50) * 0.5

            # 信号4：流畅度（多字候选）
            if cand["type"] != "char" and self.enable_fluency:
                score += self._fluency_score(phrase) * 10.0

            # 信号5：长度奖励（二字词最自然，加分）
            if len(phrase) == 2:
                score += 5.0
            elif len(phrase) > 3:
                score -= 2.0  # 长词机械组合概率高，轻微降权

            cand["_score"] = score

        # 按分数降序排列
        rest.sort(key=lambda c: c["_score"], reverse=True)

        # 移除内部字段
        for cand in candidates:
            cand.pop("_score", None)

        return mru_first + rest


# ------------------------------------------------------------------
# 便捷入口
# ------------------------------------------------------------------
_ranker = None


def get_ranker(user_data_path=None):
    """获取全局排序引擎（懒加载）。"""
    global _ranker
    if _ranker is None:
        _ranker = SemanticRanker(user_data_path=user_data_path)
    return _ranker


def rank_candidates(candidates, user_data_path=None):
    """便捷入口：排序候选列表。"""
    return get_ranker(user_data_path).rank(candidates)


if __name__ == "__main__":
    # 本地自测
    print("=== 语义排序引擎自测 ===\n")

    ranker = SemanticRanker()
    # 模拟语料（可用规则库/公开语料填充）
    ranker.feed_corpus(["你好", "人民", "中国", "世界", "企业", "工作",
                        "发展", "技术", "创新", "创业"])

    # 模拟构词引擎输出（含噪声）
    test_candidates = [
        {"phrase": "人我好", "chars": [0x4EBA, 0x6211, 0x597D], "code": "wqvb", "type": "word3"},
        {"phrase": "你好", "chars": [0x4F60, 0x597D], "code": "wqvb", "type": "word2"},
        {"phrase": "人", "chars": [0x4EBA], "code": "w", "type": "char"},
    ]

    print("排序前：")
    for c in test_candidates:
        print(f"  {c['phrase']} ({c['type']})")

    ranked = ranker.rank(test_candidates)
    print("\n排序后（期望：你好 在前）：")
    for c in ranked:
        print(f"  {c['phrase']} ({c['type']})")

    # 测试用户行为学习
    print("\n=== 用户行为学习测试 ===")
    ranker.learn_selection("人我好", 10)
    test2 = [
        {"phrase": "人我好", "chars": [1, 2, 3], "code": "wqvb", "type": "word3"},
        {"phrase": "你好", "chars": [1, 2], "code": "wqvb", "type": "word2"},
    ]
    ranked2 = ranker.rank(test2)
    print("用户常用'人我好'后排序（期望：人我好 在前）：")
    for c in ranked2:
        print(f"  {c['phrase']} ({c['type']})")

    print("\n✅ 语义排序引擎自测完成")
