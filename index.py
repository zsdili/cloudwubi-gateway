# -*- coding: utf-8 -*-
"""
CloudWubi 云端网关 - 腾讯云函数入口
====================================

职责：接收端侧客户端 POST 的 JSON（五笔编码），查询五笔编码库，
返回候选 Unicode 码点数组；支持五笔动态构词（阶段2）与语义排序（阶段3）。

请求体格式（端侧 -> 网关）：
    {"code": "wq"}                          # 单字查询
    {"code": "wqvb", "phrase": true}        # 动态构词查询
    {"code": "wqvb", "phrase": true, "learn": "你好"}  # 构词 + 用户选词学习

响应体格式（网关 -> 端侧）：
    {"code": "wq", "candidates": [20320]}
    {"code": "wqvb", "candidates": [20320, 22909], "phrases": ["你好"]}

版本演进：
- 阶段1：编码查表（内存字典 + Redis热点缓存）
- 阶段2：五笔动态构词引擎（无限组词）
- 阶段3：语义排序 + 用户行为学习（本版本新增，实现"越用越准"）
- 阶段4：场景语义、联邦自学习（规划中）
"""

import json
import os
import re

from phrase_engine import PhraseEngine, CODE_RE
from semantic_ranker import SemanticRanker


# ------------------------------------------------------------------
# 五笔编码库（阶段1：内存字典，演示用）
# 完整数据应从 cloudwubi-rules 仓库导入（wubi86_basic.txt）
# 这里内置少量高频示例，用于端到端联调
# ------------------------------------------------------------------
DEFAULT_DICT = {
    "g":   [0x4E00],            # 一
    "gggg":[0x738B],            # 王
    "fg":  [0x5730],            # 地
    "aaaa":[0x5DE5],            # 工
    "hh":  [0x4E0A],            # 上
    "jh":  [0x662F],            # 是
    "kl":  [0x4E2D],            # 中
    "mg":  [0x540C],            # 同
    "tm":  [0x4E2A],            # 个
    "wq":  [0x4F60],            # 你
    "w":   [0x4EBA],            # 人
    "e":   [0x6708],            # 月
    "r":   [0x767D],            # 白
    "t":   [0x79BE],            # 禾
    "y":   [0x8A00],            # 言
    "u":   [0x7ACB],            # 立
    "i":   [0x6C34],            # 水
    "o":   [0x706B],            # 火
    "p":   [0x4E4B],            # 之
    # 阶段2：构词演示数据（"你好" = wq vb）
    "vb":  [0x597D],            # 好
    "n":   [0x6C11],            # 民
    "aw":  [0x5171],            # 共
    "gjk": [0x754C],            # 界
    "wn":  [0x4EBA, 0x6C11],    # 人、民（演示二字词编码）
}

# 合法编码校验：1~4 位，a~y（从 phrase_engine 导入）


# ------------------------------------------------------------------
# 字典加载：优先从规则文件读取，其次使用内置默认
# ------------------------------------------------------------------
def load_dict():
    """从 cloudwubi-rules 的 wubi86_basic.txt 加载编码库。

    文件格式每行：编码 汉字 汉字 ...
    例如：wq 你 您
    """
    dict_data = dict(DEFAULT_DICT)
    rules_path = os.environ.get("CLOUDWUBI_RULES", "wubi86_basic.txt")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                code = parts[0]
                if not CODE_RE.match(code):
                    continue
                # 汉字 -> Unicode 码点
                unicode_list = [ord(ch) for word in parts[1:] for ch in word]
                if unicode_list:
                    # 追加，不覆盖默认
                    dict_data.setdefault(code, []).extend(unicode_list)
                    # 去重
                    dict_data[code] = list(dict.fromkeys(dict_data[code]))
    except FileNotFoundError:
        pass  # 文件不存在则用默认字典
    return dict_data


def load_phrase_dict():
    """加载词组规则库（wubi86_phrases.txt）：编码 -> 词组列表。"""
    phrase_data = {}
    path = os.path.join(os.path.dirname(__file__), "wubi86_phrases.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                code = parts[0]
                if not CODE_RE.match(code):
                    continue
                phrase_data[code] = parts[1:]
    except FileNotFoundError:
        pass  # 词组库不存在则仅用动态构词
    return phrase_data


WB_DICT = load_dict()
PHRASE_DICT = load_phrase_dict()

# v0.4.8 中英对照词典（云端英文翻译，1055 条高频字词）
EN_DICT = {}
try:
    _en_path = os.path.join(os.path.dirname(__file__), "en_dict.json")
    with open(_en_path, "r", encoding="utf-8") as _f:
        EN_DICT = json.load(_f)
except Exception:
    EN_DICT = {}

# 全局构词引擎与语义排序引擎实例（懒加载）
PHRASE_ENGINE = None
RANKER = None


# ------------------------------------------------------------------
# Redis 热点缓存（可选）
# ------------------------------------------------------------------
REDIS_CLIENT = None
try:
    import redis  # 可选依赖

    _redis_host = os.environ.get("REDIS_HOST")
    if _redis_host:
        REDIS_CLIENT = redis.Redis(
            host=_redis_host,
            port=int(os.environ.get("REDIS_PORT", "6379")),
            password=os.environ.get("REDIS_PASSWORD", ""),
            decode_responses=True,
            socket_connect_timeout=0.2,
        )
except ImportError:
    REDIS_CLIENT = None


def _query_with_cache(code):
    """优先查 Redis 热点缓存，未命中查字典。"""
    if REDIS_CLIENT is not None:
        try:
            cached = REDIS_CLIENT.get(f"cw:{code}")
            if cached:
                return json.loads(cached)
        except Exception:
            pass  # Redis 异常降级到字典查询

    result = WB_DICT.get(code, [])
    if result and REDIS_CLIENT is not None:
        try:
            # 缓存，TTL 7 天
            REDIS_CLIENT.setex(f"cw:{code}", 604800, json.dumps(result))
        except Exception:
            pass
    return result


# ------------------------------------------------------------------
# 腾讯云函数入口
# ------------------------------------------------------------------
def _get_phrase_engine():
    """获取构词引擎实例（懒加载，绑定单字码表+词组码表）。"""
    global PHRASE_ENGINE
    if PHRASE_ENGINE is None:
        PHRASE_ENGINE = PhraseEngine(WB_DICT, phrase_dict=PHRASE_DICT)
    return PHRASE_ENGINE


def _get_ranker():
    """获取语义排序引擎实例（懒加载，用户数据存 /tmp 便于云函数复用）。"""
    global RANKER
    if RANKER is None:
        user_data = os.environ.get("CLOUDWUBI_USER_DATA", "/tmp/cw_user_weights.json")
        RANKER = SemanticRanker(user_data_path=user_data)
        # 用规则库中的单字构建语料（提升流畅度统计）
        corpus = []
        for code, chars in WB_DICT.items():
            for cp in chars:
                ch = chr(cp)
                if len(ch) == 1:
                    corpus.append(ch)
        RANKER.feed_corpus(corpus[:2000])
    return RANKER


def main_handler(event, context):
    """腾讯云函数统一入口。

    event 结构（API 网关触发）：
        {"httpMethod": "POST", "body": "{\"code\":\"wq\"}", ...}
    """
    # 解析请求体
    body_str = ""
    if isinstance(event, dict):
        body_str = event.get("body", "") or ""
        if isinstance(body_str, (dict, list)):
            body_str = json.dumps(body_str)
    else:
        body_str = str(event or "")

    try:
        req = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid json"})

    # 用户选词学习（独立接口：{"learn": "你好"}）
    learn_phrase = req.get("learn")
    if learn_phrase:
        _get_ranker().learn_selection(learn_phrase)
        return _resp(200, {"learned": learn_phrase, "status": "ok"})

    # v0.4.8 字后联想 + 英文翻译（独立接口：{"word":"钟"} / {"word":"钟","en":true}）
    word = req.get("word")
    if word:
        resp = {"word": word}
        # 联想：词库中含该字的词组（互联网热点话题）
        engine = _get_phrase_engine()
        phrases = engine.query_by_word(word, max_results=20)
        resp["phrases"] = phrases
        # 翻译：内置中英词典（en_dict.json）
        if req.get("en"):
            resp["en"] = EN_DICT.get(word, "")
        return _resp(200, resp)

    code = (req.get("code") or "").strip().lower()
    if not CODE_RE.match(code):
        return _resp(400, {"error": "invalid code, expect 1-4 of a-y"})

    # 基础查询：单字/编码查表
    candidates = _query_with_cache(code)
    resp = {"code": code, "candidates": candidates}

    # 阶段2扩展：动态构词 + 阶段3语义排序
    if req.get("phrase"):
        engine = _get_phrase_engine()
        phrase_candidates = engine.build_phrases(code, max_results=10)

        # 阶段3增强：3码输入时，预测第4码的高频词组（前瞻预测）
        if len(code) == 3:
            # 从词库中找以当前3码为前缀的高频词组（如 "fy" -> "fyth" 云计算）
            prefix_words = []
            for pcode, words in PHRASE_DICT.items():
                if pcode.startswith(code) and words:
                    for w in words:
                        if len(w) >= 2 and w not in [c["phrase"] for c in phrase_candidates]:
                            prefix_words.append({
                                "phrase": w,
                                "chars": [ord(ch) for ch in w],
                                "code": pcode,
                                "type": "prediction",  # 第4码预测
                            })
            phrase_candidates.extend(prefix_words[:5])  # 最多补5个预测

        # 阶段3：语义排序（分层：MRU置顶+高频优先+用户行为学习+流畅度）
        ranker = _get_ranker()
        phrase_candidates = ranker.rank(phrase_candidates, code_len=len(code))
        # phrases 只含词组（长度>=2），单字仅并入 candidates（客户端显示分离）
        phrases = [p["phrase"] for p in phrase_candidates if len(p["phrase"]) >= 2]
        # 构词命中的汉字也并入候选码点
        for p in phrase_candidates:
            for cp in p["chars"]:
                if cp not in resp["candidates"]:
                    resp["candidates"].append(cp)
        resp["phrases"] = phrases

    return _resp(200, resp)


def _resp(status_code, payload):
    """构造 HTTP 响应。"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }


# 本地测试入口
if __name__ == "__main__":
    test_event = {"httpMethod": "POST", "body": json.dumps({"code": "wq"})}
    print(main_handler(test_event, None))
