# -*- coding: utf-8 -*-
"""
CloudWubi 云端网关 - 腾讯云函数入口
====================================

职责：接收端侧客户端 POST 的 JSON（五笔编码），查询五笔编码库，
返回候选 Unicode 码点数组。

请求体格式（端侧 -> 网关）：
    {"code": "wq"}

响应体格式（网关 -> 端侧）：
    {"code": "wq", "candidates": [20320, 20320]}

本版本为阶段1最小可用原型：
- 编码查询使用内存字典（演示用）
- 支持 Redis 热点缓存（若配置了 REDIS_HOST 则启用，否则用内存）
- 后续阶段2/3 在此基础上增加动态构词、语义排序、联邦训练
"""

import json
import os
import re


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
}

# 合法编码校验：1~4 位，a~y
CODE_RE = re.compile(r"^[a-y]{1,4}$")


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


WB_DICT = load_dict()


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

    code = (req.get("code") or "").strip().lower()
    if not CODE_RE.match(code):
        return _resp(400, {"error": "invalid code, expect 1-4 of a-y"})

    candidates = _query_with_cache(code)

    return _resp(200, {"code": code, "candidates": candidates})


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
