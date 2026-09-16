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
import time
import hmac
import hashlib
import urllib.request

from phrase_engine import PhraseEngine, CODE_RE, _PY_WORDS
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
    """加载词组规则库（wubi86_phrases.txt + wubi86_daily.txt 日常高频词库）：编码 -> 词组列表。"""
    phrase_data = {}
    base = os.path.dirname(os.path.abspath(__file__))
    for fname in ("wubi86_phrases.txt", "wubi86_daily.txt", "wubi86_classics.txt",
                  "wubi86_geo.txt", "wubi86_life.txt", "wubi86_mil.txt", "wubi86_poem.txt"):
        path = os.path.join(base, fname)
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
                    # v0.5.17 修复：同码多行合并（imlf 油墨 + imlf 没办法 → 两个都保留，= 覆盖会丢词）
                    if code in phrase_data:
                        phrase_data[code].extend(parts[1:])
                    else:
                        phrase_data[code] = parts[1:]
        except FileNotFoundError:
            pass  # 词组库不存在则仅用动态构词
    return phrase_data


WB_DICT = load_dict()
PHRASE_DICT = load_phrase_dict()

# v0.6.6 逗号补全联想（前句→下半句/下半段，212 组公共知识对，懒加载）
COMMA_PAIRS = None


def _get_comma_pairs():
    global COMMA_PAIRS
    if COMMA_PAIRS is None:
        try:
            with open("corpus/comma_pairs.json", encoding="utf-8") as f:
                COMMA_PAIRS = json.load(f)
        except Exception:
            COMMA_PAIRS = {}
    return COMMA_PAIRS


def comma_complete(prefix):
    """逗号后补全：精确匹配 → 前缀匹配 → 包含匹配（≤8 候选）"""
    pairs = _get_comma_pairs()
    if not pairs or not prefix:
        return []
    prefix = re.sub(r"[，,。！？、\s]", "", str(prefix))
    if len(prefix) < 2:
        return []
    out, seen = [], set()
    for s in pairs.get(prefix, []):
        if s not in seen:
            seen.add(s); out.append(s)
    if len(out) < 6:
        for k, vs in pairs.items():
            if k.startswith(prefix):
                for s in vs:
                    if s not in seen:
                        seen.add(s); out.append(s)
            if len(out) >= 8:
                break
    if len(out) < 6 and len(prefix) >= 3:
        for k, vs in pairs.items():
            if prefix in k:
                for s in vs:
                    if s not in seen:
                        seen.add(s); out.append(s)
            if len(out) >= 8:
                break
    return out[:8]

# v0.4.8 中英对照词典（云端英文翻译，121297 条，CC-CEDICT 开源）
# v0.6 优化：懒加载（SCF 128MB 内存门禁——en 接口命中才载入，省 ~80MB）
EN_DICT = None


def _get_en_dict():
    global EN_DICT
    if EN_DICT is None:
        try:
            _en_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "en_dict.json")
            with open(_en_path, "r", encoding="utf-8") as _f:
                EN_DICT = json.load(_f)
        except Exception:
            EN_DICT = {}
    return EN_DICT

# v0.6.x TMT 兜底：词典未命中时调腾讯云机器翻译（Key 存 SCF 环境变量，不落代码/仓库）
def _tmt_translate(text):
    """词典未命中 → 腾讯云 TMT 文本翻译（TC3-HMAC-SHA256 官方签名 v3）"""
    sid = os.environ.get("TMT_SECRET_ID", "")
    skey = os.environ.get("TMT_SECRET_KEY", "")
    if not sid or not skey:
        return ""
    host = "tmt.tencentcloudapi.com"; service = "tmt"
    action = "TextTranslate"; version = "2018-03-21"; region = "ap-guangzhou"
    ts = str(int(time.time()))
    date = time.strftime("%Y-%m-%d", time.gmtime(int(ts)))
    body = json.dumps({"SourceText": text, "Source": "zh", "Target": "en", "ProjectId": 0}, ensure_ascii=False)
    ct = "application/json; charset=utf-8"
    ch = "content-type:%s\nhost:%s\nx-tc-action:%s\n" % (ct, host, action.lower())
    sh = "content-type;host;x-tc-action"
    hp = hashlib.sha256(body.encode("utf-8")).hexdigest()
    cr = "\n".join(["POST", "/", "", ch, sh, hp])
    scope = "%s/%s/tc3_request" % (date, service)
    hc = hashlib.sha256(cr.encode("utf-8")).hexdigest()
    sts = "\n".join(["TC3-HMAC-SHA256", ts, scope, hc])
    def _hm(k, m):
        return hmac.new(k, m.encode("utf-8"), hashlib.sha256).digest()
    sd = _hm(("TC3" + skey).encode("utf-8"), date)
    ss = _hm(sd, service)
    sgn = _hm(ss, "tc3_request")
    sig = hmac.new(sgn, sts.encode("utf-8"), hashlib.sha256).hexdigest()
    auth = "TC3-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (sid, scope, sh, sig)
    headers = {"Authorization": auth, "Content-Type": ct, "Host": host,
               "X-TC-Action": action, "X-TC-Version": version,
               "X-TC-Timestamp": ts, "X-TC-Region": region}
    req = urllib.request.Request("https://%s/" % host, data=body.encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
            return d.get("Response", {}).get("TargetText", "")
    except Exception:
        return ""

# v0.6.x 百度翻译兜底：TMT 未命中/失败时调用（标准版免费额度，Key 存 SCF 环境变量）
def _baidu_translate(text):
    """词典→TMT 都未命中 → 百度通用翻译 API（MD5 签名）"""
    appid = os.environ.get("BAIDU_APPID", "")
    key = os.environ.get("BAIDU_KEY", "")
    if not appid or not key:
        return ""
    import urllib.parse
    salt = str(int(time.time() * 1000))
    sign = hashlib.md5((appid + text + salt + key).encode("utf-8")).hexdigest()
    params = urllib.parse.urlencode({"q": text, "from": "zh", "to": "en",
                                     "appid": appid, "salt": salt, "sign": sign})
    url = "https://fanyi-api.baidu.com/api/trans/vip/translate?" + params
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read())
            res = d.get("trans_result")
            if res:
                return res[0].get("dst", "")
    except Exception:
        pass
    return ""

# v0.5.15 反馈①：前后文顺承联想表（N-gram：前文末尾 → 后续常用词）
# 原理同豆包/微信/讯飞/百度/微软输入法联想核心（N-gram 语言模型），先科学后先进；
# 当前为常见中文搭配（模拟数据，后续用真实语料/用户输入记录升级），阳光积极向上。
SUCCESSION = {
    # 问候场景
    "早上好": ["早上好呀", "早安", "美好的一天", "早上好！"],
    "早安": ["早安！", "早上好", "新的一天开始了"],
    "早上": ["早上好", "早安", "早上好呀"],
    "中午好": ["中午好！", "午安", "好好吃饭"],
    "下午好": ["下午好！", "下午加油"],
    "晚上好": ["晚上好！", "晚安", "晚上愉快"],
    "晚安": ["晚安！", "好梦", "晚安好梦"],
    "你好": ["你好呀", "你好！", "幸会", "您好"],
    "您好": ["您好！", "您好呀", "辛苦了", "久仰"],
    # 称呼场景
    "钟总": ["钟总您好", "钟总辛苦了", "钟总早", "钟总！"],
    "老板": ["老板好", "老板辛苦了", "老板英明"],
    "老师": ["老师好", "老师辛苦了", "老师您好"],
    "同学": ["同学好", "同学们好", "同学加油"],
    # 感谢场景
    "谢谢": ["谢谢您", "谢谢！", "非常感谢", "多谢"],
    "感谢": ["感谢您", "非常感谢", "感恩"],
    # 鼓励场景
    "加油": ["加油！", "加油呀", "一起加油"],
    "努力": ["努力加油", "努力奋斗", "继续努力"],
    "坚持": ["坚持就是胜利", "坚持下去", "坚持到底"],
    "辛苦": ["辛苦了", "辛苦了！", "辛苦啦"],
    # 工作/事业场景
    "工作": ["工作顺利", "工作加油", "工作辛苦了"],
    "创业": ["创业顺利", "创业加油", "创业成功"],
    "项目": ["项目进展", "项目顺利", "项目推进"],
    "会议": ["会议纪要", "会议安排", "会议开始"],
    # 用户历史反馈场景（v0.5.11 前进搭配 / v0.4.9 陈胜吴广链 / v0.4.x 宇宇宙）
    "前进": ["前进的方向", "前进路上", "前进吧", "前进号角", "继续前进"],
    "进": ["进一步", "进行", "进展", "进度", "进来"],
    "陈胜": ["陈胜吴广", "陈胜起义"],
    "吴广": ["陈胜吴广", "吴广起义"],
    "宇": ["宇宙", "宇航", "宇航员", "宇宙飞船"],
    "钟": ["钟总", "钟声", "钟情", "钟意"],
    # 生活场景
    "天气": ["天气真好", "天气不错", "天气预报", "天气晴朗"],
    "今天": ["今天天气", "今天怎么样", "今天的工作", "今天加油"],
    "明天": ["明天见", "明天加油", "明天继续"],
    "新年": ["新年快乐", "新年吉祥", "新年大吉"],
    # 祝愿场景
    "健康": ["身体健康", "健康快乐", "健康平安"],
    "幸福": ["幸福安康", "幸福快乐", "幸福美满"],
    "快乐": ["快乐每一天", "天天快乐", "快乐平安"],
    "平安": ["平安健康", "一路平安", "平安喜乐"],
    "吉祥": ["吉祥如意", "大吉大利", "吉祥安康"],
    "如意": ["万事如意", "吉祥如意", "顺心如意"],
    "梦想": ["梦想成真", "追逐梦想", "实现梦想"],
    "成功": ["成功在望", "祝您成功", "取得成功"],
}


# v0.6 反馈①②：互联网热词 + 未来趋势词表（2025-2027，中性积极，科技/生活/发展）
# 用于上下文连续联想（结合输入框上文，非单字联想）
HOT_WORDS = [
    "人工智能", "大模型", "智能体", "算力", "云计算", "云原生", "大数据", "机器学习", "深度学习",
    "量子计算", "元宇宙", "数字人", "机器人", "自动驾驶", "低空经济", "具身智能", "无人机",
    "新能源", "绿色能源", "双碳", "光伏", "储能", "新能源汽车", "芯片", "半导体",
    "数字经济", "新质生产力", "高质量发展", "一带一路", "共同富裕", "中国式现代化",
    "健康", "幸福", "美好生活", "创新", "创业", "奋斗", "梦想", "希望", "未来",
    "成功", "成长", "进步", "发展", "合作", "共赢", "价值", "使命", "贡献",
    "智慧城市", "数字中国", "智能制造", "工业互联网", "网络安全", "生物科技", "太空探索",
    "文化自信", "科技创新", "人才强国", "教育强国", "体育强国", "健康中国",
    # v0.5.33 每日热词层（2026-09-14 真实热点，86 规则自动算码）
    "服务贸易", "秋粮生产", "金砖合作", "全球南方", "统筹监测", "复合型人才", "服贸会", "算力统筹",
]


NEG_WORDS = ("智障", "梦魇", "前功尽弃", "落魄", "倒霉", "糟糕", "失败", "完蛋", "悲剧",
           "恐怖", "灾难", "痛苦", "绝望", "阴暗", "负能量", "沮丧", "抑郁", "疾病", "癌症",
           "春梦", "魂牵梦萦", "黄粱", "南柯", "大梦初醒", "梦露", "梦游", "愚蠢", "愚昧",
           "堕落", "沉沦", "骗子", "诈骗", "虚伪", "丑陋", "悲惨", "丧气", "丧钟", "毁弃",
           "老态龙钟", "悬钟", "警钟", "死人", "火葬场", "走后门", "尸体", "丧事", "凶杀",
           "抢劫", "偷窃", "殴打", "吸毒", "赌博", "嫖娼", "卖淫", "强奸", "猥亵")



# ========== v0.5.25 云端热词 ==========
# 互联网热点词（2025-2026 趋势 + 通用高频），按 86 规则自动算码并入候选
HOT_WORDS = [
    "人工智能", "大模型", "云计算", "算力", "新质生产力", "低空经济", "银发经济", "数字化转型",
    "新能源", "芯片", "开源", "鸿蒙", "碳中和", "数字经济", "数据要素", "智能制造",
    "机器人", "无人机", "直播", "短视频", "电商", "物流", "供应链", "创业", "融资", "投资",
    "股权", "上市", "中概股", "元宇宙", "区块链", "自动驾驶", "智能驾驶", "固态电池", "折叠屏",
    "卫星互联网", "脑机接口", "量子计算", "光刻机", "半导体", "国产替代", "专精特新", "独角兽",
    "出海", "跨境电商", "情绪价值", "松弛感", "多巴胺", "首发经济", "谷子经济", "夜经济",
    "实战", "落地", "干货", "爆款", "流量", "私域", "转化率", "商业模式",
    "钟志胜", "云五笔", "豆包", "抖音", "微信", "小红书", "自媒体", "广东", "通达",
    "创业加速器", "钟总", "大湾区", "直播带货", "出海",
    # v0.5.33 每日热词层（2026-09-14 真实热点，fetch_daily_hot.py 固化机制）
    "服务贸易", "秋粮生产", "金砖合作", "全球南方", "统筹监测", "复合型人才", "服贸会", "算力统筹"
]
# v0.5.64 修复：每日热词文件（fetch_hot_daily.py 自动入库）与硬编码合并加载
DAILY_HOT = {}   # v0.5.64：热词码映射（code 打字出词）
try:
    import os as _os
    # v0.5.65：SCF 环境路径差异——多候选路径（__file__ 目录 / cwd / /var/user）
    _dhp = None
    for _p in (_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "daily_hot_words.json"),
               _os.path.join(_os.getcwd(), "daily_hot_words.json"),
               "/var/user/daily_hot_words.json"):
        if _os.path.exists(_p):
            _dhp = _p
            break
    if _dhp:
        _dh = json.load(open(_dhp, encoding="utf-8"))
        for _w in _dh.keys():
            if _w not in HOT_WORDS:
                HOT_WORDS.append(_w)
        DAILY_HOT = _dh
except Exception:
    pass

ASSOC_LINK = {}
try:
    import os as _os2
    _alp = _os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)), "assoc_link.json")
    if _os2.path.exists(_alp):
        ASSOC_LINK = json.load(open(_alp, encoding="utf-8"))
except Exception:
    pass

# v0.7.2 LLM 语料强化：情景联想包（诗词对/歇后语对/生活对话，succession_extra.json）
try:
    _sep = _os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)), "succession_extra.json")
    if _os2.path.exists(_sep):
        SUCCESSION.update(json.load(open(_sep, encoding="utf-8")))
except Exception:
    pass

# v0.6 革命性：n-gram 概率映射表（离线自动学习自训练语料，213 条 9.6KB）
#   生病了→看医生/想去医院；前进→方向/号角/浪潮；想→办法/一下/你
NGRAM_LINK = {}
try:
    _nlp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ngram_link.json")
    if os.path.exists(_nlp):
        NGRAM_LINK = json.load(open(_nlp, encoding="utf-8"))
except Exception:
    pass


def _ngram_link_associate(text, max_results=6):
    """n-gram 概率映射查询：末尾 3→1 字子串最长匹配（词级键+字级退化都覆盖）
    返回语义衔接后续词（概率排序）"""
    t = (text or "").strip()
    if not t:
        return []
    for n in (3, 2, 1):
        key = t[-n:] if len(t) >= n else t
        if key in NGRAM_LINK:
            return [w for w in NGRAM_LINK[key] if len(w) >= 2][:max_results]
    return []

def _load_hot_by_code():
    """热点词按 86 规则算码：2字=前2+前2；3字=1+1+2；4字=1+1+1+1"""
    code_map = {}
    basic = {}
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        if not os.path.exists(os.path.join(_base, "wubi86_basic.txt")):
            _base = os.getcwd()  # SCF 环境兜底
        for line in open(os.path.join(_base, "wubi86_basic.txt"), encoding="utf-8"):
            parts = line.strip().split()
            if len(parts) >= 2:
                for ch in parts[1:]:
                    basic.setdefault(ch, parts[0])  # 字 -> 全码（规则库格式：码 字1 字2 ...）
    except Exception:
        pass
    def fc(ch):
        c = basic.get(ch)
        return c if c else ""
    for w in HOT_WORDS:
        n = len(w)
        if n == 2:
            c = (fc(w[0])[:2] + fc(w[1])[:2])[:4]
        elif n == 3:
            c = (fc(w[0])[:1] + fc(w[1])[:1] + fc(w[2])[:2])
        elif n >= 4:
            c = fc(w[0])[:1] + fc(w[1])[:1] + fc(w[2])[:1] + fc(w[-1])[:1]  # 86 多字词：前3字各1码+末字1码
        else:
            continue
        if len(c) == 4:
            code_map.setdefault(c, []).append(w)
    return code_map

HOT_BY_CODE = _load_hot_by_code()

# v0.5.47：86 版 25 键一级简码（1 码 hot 强制第一）
SIMPLE1 = {"g":"一","f":"地","d":"在","s":"要","a":"工","h":"上","j":"是","k":"中","l":"国",
           "m":"同","t":"和","r":"的","e":"有","w":"人","q":"我","y":"主","u":"产","i":"不",
           "o":"为","p":"这","n":"民","b":"了","v":"发","c":"以","x":"经"}

def _load_category_by_code():
    """v0.5.31 分类词库（category_words.json 已按 86 规则预计算码）：码 -> [(词, 分类)]"""
    cat_map = {}
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        if not os.path.exists(os.path.join(_base, "category_words.json")):
            _base = os.getcwd()  # SCF 容器兜底
        data = json.load(open(os.path.join(_base, "category_words.json"), encoding="utf-8"))
        for cat, items in data.items():
            for it in items:
                c = it.get("c", "")
                if len(c) == 4:
                    cat_map.setdefault(c, []).append((it["w"], cat))
    except Exception:
        pass
    return cat_map

CAT_BY_CODE = _load_category_by_code()

def _cat_stats():
    """分类词库规模统计（词条数上报用）"""
    cats = set()
    tot = 0
    for c, items in CAT_BY_CODE.items():
        for w, cat in items:
            cats.add(cat)
            tot += 1
    return len(cats), tot

CATEGORY_CATS, CATEGORY_TOTAL = _cat_stats()

# v0.5.35 反馈⑥：拼音/简拼混打词库（py_full.json 全拼索引 + py_short.json 简拼索引）
def _load_pinyin():
    pyf, pys = {}, {}
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        if not os.path.exists(os.path.join(_base, "py_full.json")):
            _base = os.getcwd()
        if os.path.exists(os.path.join(_base, "py_full.json")):
            pyf = json.load(open(os.path.join(_base, "py_full.json"), encoding="utf-8"))
        if os.path.exists(os.path.join(_base, "py_short.json")):
            pys = json.load(open(os.path.join(_base, "py_short.json"), encoding="utf-8"))
    except Exception:
        pass
    return pyf, pys

PY_FULL, PY_SHORT = _load_pinyin()

# v0.5.36 反馈⑦：高频字统计推送——freq.json（3500 常用字频排名）驱动单字候选排序
def _load_freq():
    fr = {}
    try:
        _base = os.path.dirname(os.path.abspath(__file__))
        if not os.path.exists(os.path.join(_base, "freq.json")):
            _base = os.getcwd()
        if os.path.exists(os.path.join(_base, "freq.json")):
            fr = json.load(open(os.path.join(_base, "freq.json"), encoding="utf-8"))
    except Exception:
        pass
    return fr

FREQ = _load_freq()

HOT_DAILY = set("不等于 去哪里 反馈 辛苦了 谢谢你 对不起 不客气 没关系 没问题 来得及 舍不得 办公室 怎么办 为什么 怎么 可以 工作 学习 中国 人民 我们 你们 他们 今天 明天 昨天 现在 时候 知道 觉得 喜欢 希望 需要 应该 可以 能够 知道 了解 支持 帮助 成功 幸福 快乐 健康 加油 努力 谢谢 您好 你好 早上好 中午好 晚上好 再见 恭喜 欢迎 请问 谢谢 抱歉 感谢 大家 朋友 时间 生活 世界 国家 社会 发展 建设 创新 创业 科技 智能 未来 区块链 数字经济 创业创新 投资基金 项目孵化 智能体 数字化 人工智能 云计算 大数据 互联网 物联网 大模型 供应链 加速器 创始人 商业模式 独角兽 科创板 新能源 碳中和 机器人 无人机 跨境电商 直播电商 新质生产力 高质量发展 共同富裕 自主可控 国产替代 专精特新 数据要素 机器学习 深度学习 大语言模型 数字人 智慧城市 乡村振兴 消费升级 品牌出海".split())


def _sort_phrases_by_freq(phrases):
    """词组排序（v0.5.41 反馈②/⑥）：高频日常用语置顶 → 拼音词库词（真实常用词）→ 其他（字频和升序）。
    非词典词/低频组合自动后移；3 码场景只保留常用词（过滤见 main_handler）。"""
    try:
        fr = _load_freq()
        py = _PY_WORDS()
        def wsum(w):
            return sum(fr.get(ch, 99999) for ch in w)
        hot = [p for p in phrases if p in HOT_DAILY]
        rest = [p for p in phrases if p not in HOT_DAILY]
        py_rest = [p for p in rest if p in py]
        other = [p for p in rest if p not in py]
        py_rest.sort(key=wsum)
        other.sort(key=wsum)
        return hot + py_rest + other
    except Exception:
        return phrases


def _sort_by_freq(cands):
    """单字候选按高频字排名排序（排名小=高频在前；无频率字排后）"""
    if not cands or len(cands) < 2:
        return cands
    def keyf(cp):
        ch = chr(cp)
        r = FREQ.get(ch)
        return (0 if r else 1, r if r else 99999)
    return sorted(cands, key=keyf)

def _filter_pos(words):
    """过滤消极/阴暗词（用户固化：阳光、积极向上、有启发有感悟）"""
    return [w for w in words if not any(n in w for n in NEG_WORDS)]


# v0.5.76 城市知识联想（真实搭配，算法即库——动态生成，无需词库）
CITY_KNOWLEDGE = {'广州': ['广州塔', '广州地铁', '广州美食', '广州欢迎你', '广州市', '广州天气', '广州房价', '广州白云机场', '广州火车站', '广州大学城'], '北京': ['北京故宫', '北京烤鸭', '北京地铁', '北京欢迎你', '北京市', '北京天气', '北京房价', '北京大兴机场', '北京胡同', '北京大学'], '上海': ['上海外滩', '上海迪士尼', '上海地铁', '上海美食', '上海市', '上海天气', '上海房价', '上海虹桥机场', '上海浦东', '上海交通大学'], '深圳': ['深圳湾', '深圳速度', '深圳地铁', '深圳大学', '深圳市', '深圳天气', '深圳房价', '深圳宝安机场', '深圳科技园', '深圳人才公园'], '成都': ['成都大熊猫', '成都火锅', '成都地铁', '成都美食', '成都市', '成都天气', '成都房价', '成都双流机场', '成都宽窄巷子', '成都太古里'], '杭州': ['杭州西湖', '杭州地铁', '杭州美食', '杭州市', '杭州天气', '杭州房价', '杭州萧山机场', '杭州灵隐寺', '杭州宋城', '杭州亚运会'], '武汉': ['武汉樱花', '武汉热干面', '武汉地铁', '武汉美食', '武汉市', '武汉天气', '武汉房价', '武汉天河机场', '武汉黄鹤楼', '武汉大学'], '西安': ['西安兵马俑', '西安肉夹馍', '西安地铁', '西安美食', '西安市', '西安天气', '西安房价', '西安咸阳机场', '西安大雁塔', '西安城墙'], '重庆': ['重庆火锅', '重庆洪崖洞', '重庆地铁', '重庆美食', '重庆市', '重庆天气', '重庆房价', '重庆江北机场', '重庆小面', '重庆解放碑'], '南京': ['南京夫子庙', '南京中山陵', '南京地铁', '南京美食', '南京市', '南京天气', '南京房价', '南京禄口机场', '南京盐水鸭', '南京大学'], '长沙': ['长沙臭豆腐', '长沙橘子洲', '长沙地铁', '长沙美食', '长沙市', '长沙天气', '长沙房价', '长沙黄花机场', '长沙茶颜悦色', '长沙岳麓山'], '厦门': ['厦门鼓浪屿', '厦门地铁', '厦门美食', '厦门市', '厦门天气', '厦门房价', '厦门高崎机场', '厦门大学', '厦门环岛路', '厦门曾厝垵'], '青岛': ['青岛啤酒', '青岛栈桥', '青岛地铁', '青岛美食', '青岛市', '青岛天气', '青岛房价', '青岛流亭机场', '青岛五四广场', '青岛崂山'], '哈尔滨': ['哈尔滨冰雪大世界', '哈尔滨红肠', '哈尔滨地铁', '哈尔滨美食', '哈尔滨市', '哈尔滨天气', '哈尔滨房价', '哈尔滨太平机场', '哈尔滨中央大街', '哈尔滨冰灯'], '天津': ['天津狗不理', '天津之眼', '天津地铁', '天津美食', '天津市', '天津天气', '天津房价', '天津滨海机场', '天津五大道', '天津煎饼果子'], '苏州': ['苏州园林', '苏州刺绣', '苏州地铁', '苏州美食', '苏州市', '苏州天气', '苏州房价', '苏州机场', '苏州评弹', '苏州博物馆'], '东莞': ['东莞制造', '东莞地铁', '东莞美食', '东莞市', '东莞天气', '东莞房价', '东莞松山湖', '东莞虎门', '东莞篮球', '东莞理工学院'], '佛山': ['佛山武术', '佛山陶都', '佛山地铁', '佛山美食', '佛山市', '佛山天气', '佛山房价', '佛山祖庙', '佛山顺德', '佛山岭南天地'], '中山': ['中山故居', '中山灯饰', '中山美食', '中山市', '中山天气', '中山房价', '中山站', '中山影视城', '中山詹园', '中山石岐乳鸽'], '珠海': ['珠海长隆', '珠海渔女', '珠海地铁', '珠海美食', '珠海市', '珠海天气', '珠海房价', '珠海金湾机场', '珠海情侣路', '珠海横琴'], '惠州': ['惠州西湖', '惠州双月湾', '惠州美食', '惠州市', '惠州天气', '惠州房价', '惠州机场', '惠州巽寮湾', '惠州罗浮山', '惠州大亚湾'], '汕头': ['汕头牛肉丸', '汕头南澳岛', '汕头美食', '汕头市', '汕头天气', '汕头房价', '汕头机场', '汕头小公园', '汕头工夫茶', '汕头潮汕'], '江门': ['江门碉楼', '江门陈皮', '江门美食', '江门市', '江门天气', '江门房价', '江门站', '江门小鸟天堂', '江门古劳水乡', '江门开平'], '肇庆': ['肇庆七星岩', '肇庆裹蒸粽', '肇庆美食', '肇庆市', '肇庆天气', '肇庆房价', '肇庆站', '肇庆鼎湖山', '肇庆砚都', '肇庆端砚'], '昆明': ['昆明四季如春', '昆明滇池', '昆明美食', '昆明市', '昆明天气', '昆明房价', '昆明长水机场', '昆明鲜花', '昆明石林', '昆明翠湖'], '郑州': ['郑州烩面', '郑州地铁', '郑州美食', '郑州市', '郑州天气', '郑州房价', '郑州新郑机场', '郑州二七塔', '郑州黄河', '郑州大学'], '济南': ['济南趵突泉', '济南大明湖', '济南美食', '济南市', '济南天气', '济南房价', '济南遥墙机场', '济南千佛山', '济南把子肉', '济南大学'], '福州': ['福州三坊七巷', '福州鱼丸', '福州美食', '福州市', '福州天气', '福州房价', '福州长乐机场', '福州鼓山', '福州茉莉花', '福州大学'], '南宁': ['南宁老友粉', '南宁青秀山', '南宁美食', '南宁市', '南宁天气', '南宁房价', '南宁吴圩机场', '南宁中山路', '南宁会展中心', '南宁大学'], '海口': ['海口骑楼', '海口海鲜', '海口美食', '海口市', '海口天气', '海口房价', '海口美兰机场', '海口假日海滩', '海口火山口', '海口万绿园']}


def context_associate(text, max_results=20):
    """v0.6/v0.5.15 反馈①②：上下文连续联想（革命性核心）
    输入：输入框光标前 N 字（整句上文）
    返回：基于上文的连续联想——
      v0.5.15 优先：前后文顺承联想（N-gram：整句末尾最长匹配顺承表，前文→后续）
      未命中时回退：bigram 后缀 + 单字后缀 + 成语启发 + 热词趋势
    不再单字联想，而是结合前后文语境。
    """
    text = (text or "").strip()
    if not text:
        return []
    # v0.5.15 反馈① + v0.7.3 整句优先：前后文顺承——整句末尾从长到短匹配（整句长度→1字，上限8字）
    #   修复缺口：5-7 字整句（山重水复疑无路/哑巴吃黄连）此前只查末1-4字永远不命中
    for n in range(min(8, len(text)), 0, -1):
        key = text[-n:] if len(text) >= n else text
        if key in SUCCESSION:
            return SUCCESSION[key][:max_results]
    # v0.5.66 创新：意思衔接表（ima 语义级 + Kimi 打分思想的本地实现）——
    #   末 3 字/末 2 字/末 1 字查 ASSOC_LINK（辛苦了→钟总/大家/你；前进→方向/道路/号角/浪潮/脚步），
    #   排位在成语/热词/bigram 之前（"衔接"比"组词"更贴语义延续）
    for n in (3, 2, 1):
        key = text[-n:] if len(text) >= n else text
        if key in ASSOC_LINK:
            return [w for w in ASSOC_LINK[key]][:max_results]
    # v0.6 革命性：n-gram 概率映射层（自动学习自训练语料，比手写表覆盖更大）
    #   生病了→看医生/想去医院；想→办法/一下/你；学习→知识/向上/奋斗
    # v0.5.76 城市知识联想：末 2 字命中城市 → 动态给出该城真实搭配（算法即库，无需词库）
    for _n in (2, 1):
        _key = text[-_n:] if len(text) >= _n else text
        if _key in CITY_KNOWLEDGE:
            return CITY_KNOWLEDGE[_key][:max_results]
    _ng = _ngram_link_associate(text, max_results)
    if _ng:
        return _ng
    tail = text[-2:] if len(text) >= 2 else text[-1:]
    last1 = tail[-1]
    engine = _get_phrase_engine()
    out = []
    seen = set()

    def add(w):
        if w and len(w) >= 2 and w not in seen:
            seen.add(w)
            out.append(w)

    # ① 成语/金句启发：含末 1 字的 4 字词（阳光向上，眼前一亮——用户 v0.6 反馈核心）
    for p in engine.query_by_word(last1, 10):
        if len(p) == 4:
            add(p)
    # ② 热词/趋势词：含末 1 字或末 2 字（互联网热点 + 未来趋势，与时俱进）
    for w in HOT_WORDS:
        if last1 in w or (len(tail) == 2 and tail in w):
            add(w)
    # ③ bigram 后缀：以末 2 字开头的词组（语境顺承：前进→前进浪潮/前进号角）
    if len(tail) == 2:
        for p in engine.query_by_prefix(tail, 8):
            add(p)
    # ④ 单字后缀：以末 1 字开头的常用搭配（兜底）
    for p in engine.query_by_prefix(last1, 8):
        add(p)
    # ⑤ 用户近期学习词（云端 learn_selection 的 MRU 记录，最近在前）
    try:
        for w in _get_ranker().mru:
            add(w)
    except Exception:
        pass
    # v0.6 革命性：kenlm n-gram 概率重排——语义衔接词前移、组词/无关词垫底
    #   验证数据：前进+方向=-2.2 / 前进+进行=-102（语料从未共现 → 自动过滤）
    _pool = _filter_pos(out)[:max_results]
    _pool = _ngram_rescore(text, _pool)
    return _pool[:max_results]


# 全局构词引擎与语义排序引擎实例（懒加载）
PHRASE_ENGINE = None
RANKER = None


# ------------------------------------------------------------------
# v0.6 革命性：kenlm n-gram 概率联想层（LGPL-2.1，开源免费）
#   作用：对候选池做条件概率重排——语义衔接词前移、组词/无关词垫底
#   model2.arpa 为纯 Python 训练器（MLE+回退）产物，46KB
# ------------------------------------------------------------------
KENLM_MODEL = None


def _get_kenlm():
    """懒加载 kenlm 模型（SCF 环境有包则启用，无则静默降级）"""
    global KENLM_MODEL
    if KENLM_MODEL is None:
        try:
            import kenlm
            _mp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model2.arpa")
            if os.path.exists(_mp):
                KENLM_MODEL = kenlm.Model(_mp)
                print("kenlm n-gram 模型已加载:", os.path.getsize(_mp), "B")
        except Exception as e:  # 包缺失/加载失败 → 降级手写表
            print("kenlm 不可用(降级):", e)
            KENLM_MODEL = False
    return KENLM_MODEL if KENLM_MODEL else None


def _ngram_rescore(ctx_text, cands, topk=8):
    """kenlm 字级 3-gram 条件概率重排（无分词、无 OOV，中文主流做法）
    P(候选前2字|上文末1字) + 0.5·P(候选首字|上文末2字)
    语义衔接词前移；-100 级（语料从未共现）垫底过滤"""
    km = _get_kenlm()
    if km is None or not cands:
        return cands
    tail2 = ctx_text[-2:] if len(ctx_text) >= 2 else ctx_text
    tail1 = ctx_text[-1:] if ctx_text else ""
    scored = []
    for w in cands:
        if len(w) >= 2:
            s = km.score("%s %s" % (tail1, w[:2]), bos=False, eos=False)
        else:
            s = km.score("%s %s" % (tail1, w), bos=False, eos=False)
        s3 = km.score("%s %s %s" % (tail2[0], tail2[1], w[0]), bos=False, eos=False)
        scored.append((w, s + 0.5 * s3))
    scored.sort(key=lambda x: -x[1])
    kept = [w for w, s in scored if s > -90]
    for w, s in scored:  # 保底：不足时补回
        if w not in kept:
            kept.append(w)
    return kept[:topk]


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
        resp["phrases"] = _filter_pos(phrases)
        # 翻译：v0.6.8 候选数组整词优先（{"words":["是国庆节","国庆节","庆节","节"],"en":true}）
        #   逐个查词典，第一个命中返回（国庆节→PRC National Day）；全未命中→末字 TMT/百度兜底（不翻整句）
        if req.get("en"):
            cands = req.get("words") or ([word] if word else [])
            en_out = ""
            for cw in cands:
                if not cw: continue
                en_out = _get_en_dict().get(cw, "")
                if en_out: break
            if not en_out and cands:
                last = cands[-1]
                # v0.5.74：末字非中文（数字/符号）不兜底——"不是字就不翻译"
                if last and re.search(r'[\u4e00-\u9fff]', last):
                    en_out = _get_en_dict().get(last, "") or _tmt_translate(last) or _baidu_translate(last)
            resp["en"] = en_out
        return _resp(200, resp)

    # v0.6 反馈①②：上下文连续联想（独立接口：{"context":"我最近在了解人工智能"}）
    ctx = req.get("context")
    if ctx:
        phrases = context_associate(str(ctx))
        return _resp(200, {"context": str(ctx), "phrases": phrases})

    # v0.6.6 逗号补全联想（独立接口：{"comma":"床前明月光"} → 下半句/下半段）
    cma = req.get("comma")
    if cma:
        return _resp(200, {"comma": str(cma), "phrases": comma_complete(str(cma))})

    # v0.6.3 CCA 联动增强：客户端拉取全量衔接映射表（云端规则实时生效，免发版）
    if req.get("linkmap"):
        return _resp(200, {"links": NGRAM_LINK})

    # v0.5.35 反馈⑥：拼音/简拼混打（独立接口：{"py":"nihao"} / {"py":"ywb"}）
    py = req.get("py")
    if py:
        pystr = str(py).strip().lower()
        resp = {"py": pystr}
        merged, seen = [], set()
        if len(pystr) >= 2:
            for w in PY_FULL.get(pystr, [])[:12]:
                if w not in seen:
                    seen.add(w); merged.append(w)
            for w in PY_SHORT.get(pystr, [])[:10]:
                if w not in seen:
                    seen.add(w); merged.append(w)
        resp["phrases"] = merged
        return _resp(200, resp)

    # v0.4.9 连续联想（独立接口：{"prefix":"陈胜"} → 以该前缀开头的词组）
    prefix = req.get("prefix")
    if prefix:
        engine = _get_phrase_engine()
        phrases = _filter_pos(engine.query_by_prefix(prefix, max_results=20))
        return _resp(200, {"prefix": prefix, "phrases": phrases})

    code = (req.get("code") or "").strip().lower()
    if not CODE_RE.match(code):
        return _resp(400, {"error": "invalid code, expect 1-4 of a-y"})

    # 基础查询：单字/编码查表
    candidates = _query_with_cache(code)
    # v0.5.64：每日热词 86 码出词（thta→延长；不占普通词库码位）
    if not candidates and DAILY_HOT:
        for _w, _c in DAILY_HOT.items():
            if _c == code:
                candidates.append({"phrase": _w, "chars": [ord(ch) for ch in _w],
                                   "code": code, "type": "hot"})
                if len(candidates) >= 3:
                    break
    resp = {"code": code, "candidates": candidates}
    if req.get("dbg"):
        resp["dbg_daily"] = len(DAILY_HOT)

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
        # v0.5.31 分类词库：同码分类词并入（每码最多3条，优先于热词/基础词，带分类名）
        cat_added = 0
        for cw, ccat in CAT_BY_CODE.get(code, []):
            if cw not in [p["phrase"] for p in phrase_candidates]:
                phrase_candidates.append({"phrase": cw, "score": 95, "type": "lexicon",
                                          "chars": [ord(ch) for ch in cw], "cat": ccat})
                cat_added += 1
                if cat_added >= 3:
                    break
        # v0.5.25 云端热词：同码热点词并入候选（排在构词/预测之后，语义联想之前）
        for hw in HOT_BY_CODE.get(code, []):
            if hw not in [p["phrase"] for p in phrase_candidates]:
                phrase_candidates.append({"phrase": hw, "score": 90, "type": "lexicon",
                                          "chars": [ord(ch) for ch in hw]})
        # v0.5.64 每日热词 86 码出词（thta→延长；type=hot 优先显示、不并入单字候选避免类型污染）
        if DAILY_HOT:
            for _w, _c in DAILY_HOT.items():
                if _c == code and _w not in [p["phrase"] for p in phrase_candidates]:
                    phrase_candidates.insert(0, {"phrase": _w, "score": 96, "type": "hot",
                                                 "chars": [ord(ch) for ch in _w]})
                    break
        # phrases 只含词组（长度>=2），单字仅并入 candidates（客户端显示分离）
        # v0.5.17 反馈②③（举一反三）：词组分组——真词组（lexicon/prediction）进 phrases（优先显示）
        # v0.5.22（用户反馈"常用词库未正确显示"）：禁用动态构词 gen——
        #   dugj 等无词库真词的编码不再返回"在立理/磁理"类无意义组合，宁可无候选提示打错，
        #   词库真词（lexicon/prediction）照常显示；未来若需"无限组词"可恢复本分支
        phrases = [p["phrase"] for p in phrase_candidates
                   if len(p["phrase"]) >= 2 and p["type"] in ("lexicon", "prediction", "hot")]
        # v0.5.31 分类词优先：带 cat 的分类词移到 phrases 最前（用户打码即见分类词）
        cat_phrases = [p["phrase"] for p in phrase_candidates if p.get("cat") and len(p["phrase"]) >= 2]
        if cat_phrases:
            phrases = cat_phrases + [p for p in phrases if p not in cat_phrases]
        gen = []
        # v0.5.22：候选码点只并入真词（lexicon/prediction）的汉字——动态构词字不再混入
        #   （dugj 无真词时 candidates 保持单字表精确结果，不再出现"磁立理"类组合字）
        for p in phrase_candidates:
            if p["type"] in ("lexicon", "prediction"):
                for cp in p["chars"]:
                    if cp not in resp["candidates"]:
                        resp["candidates"].append(cp)
        resp["phrases"] = phrases
        if gen:
            resp["gen"] = gen
        # v0.5.31 词条数上报：云端分类词库规模（客户端"云五笔"弹窗显示）
        resp["cat_count"] = CATEGORY_CATS
        resp["cat_words"] = CATEGORY_TOTAL

    # v0.5.36 反馈⑦ + v0.5.38 落实：高频字统计推送——单字候选按字频排序 + hot 字段推给前端
    # v0.5.40 反馈⑦ + v0.5.41 反馈②：词组排序 + 3 码只保留常用词（HOT_DAILY + 拼音词库词），生僻组合不显示
    if resp.get("phrases"):
        if len(code) < 4:
            py = _PY_WORDS()
            resp["phrases"] = [p for p in resp["phrases"] if p in HOT_DAILY or p in py]
        if len(resp["phrases"]) > 1:
            resp["phrases"] = _sort_phrases_by_freq(resp["phrases"])
    if resp.get("candidates"):
        resp["candidates"] = _sort_by_freq(resp["candidates"])
        # v0.5.41 反馈⑥：hot 优先取本编码 basic 单字（精确字频 top6，避免词库字符污染如 suf→无/相/场）
        # v0.5.47 顽疾根治：1 码时一级简码字强制 hot 第一（打 r → hot 第一必为"的"，键名字/字根字不得压过简码）
        hot = []
        for cp in WB_DICT.get(code, []):
            ch = chr(cp)
            if len(ch) == 1 and FREQ.get(ch):
                hot.append(ch)
            if len(hot) >= 6:
                break
        if not hot:
            for cp in resp["candidates"]:
                if not isinstance(cp, int):   # v0.5.64：防御 dict 混入（词组候选只走 phrases）
                    continue
                ch = chr(cp)
                if len(ch) == 1 and FREQ.get(ch):
                    hot.append(ch)
                if len(hot) >= 6:
                    break
        if hot:
            hot.sort(key=lambda ch: (0 if (len(code) == 1 and SIMPLE1.get(code) == ch) else 1,
                                     FREQ.get(ch, 9999)))
            resp["hot"] = hot
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
