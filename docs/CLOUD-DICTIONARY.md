# 云五笔云端词库分层清单（v0.7.10）

用户固化：**三字及以上词全部放云端**（减小 APK），端侧仅保留字根字 + 一/二/三级简码 + 全码单字 + 高频二字词。

## 云端词库（gateway-repo/）
| 文件 | 规模 | 内容 | 86 码来源 |
|---|---|---|---|
| wubi86_phrases.txt | 111,127 词 | 通用词组库（二字为主） | 官方/主流词库 |
| wubi86_basic.txt | 26,281 单字 | 字根字+一/二/三级简码+全码 | 86 版官方 |
| wubi86_3char.json | 349 词 | 三字日常用语+三字成语 | 构词公式 |
| wubi86_migrated.json | 138 词 | 端侧迁移三/四字词 | 端侧原码 |
| wubi86_song.json | 72 词 | 歌名 | 构词公式 |
| wubi86_webstar.json | 90 词 | 网红/明星名 | 构词公式 |
| wubi86_street.json | 128 词 | 街道/地标 | 构词公式 |
| wubi86_estate.json | 80 词 | 小区/楼盘 | 构词公式 |
| wubi86_food.json | 133 词 | 小吃/美食 | 构词公式 |
| wubi86_brand.json | 183 词 | 知名品牌 | 构词公式 |
| wubi86_mingyan.json | 103 词 | 名言名句 | 构词公式 |
| wubi86_xiehouyu.json | 118 词 | 歇后语/典故 | 构词公式 |
| wubi86_qingming.json | 136 词 | 明清短句/古典 | 构词公式 |
| wubi86_classics.txt | 939 行 | 经典名句 | 人工整理 |
| wubi86_poem.txt | — | 唐诗宋词 | 人工整理 |
| wubi86_geo.txt | — | 城市/地名 | 人工整理 |
| wubi86_daily.txt | — | 每日词 | 热词 |
| wubi86_meme.json | 216 词 | 谐音梗/网红段子 | 构词公式 |
| wubi86_contrib.txt | — | 用户贡献词 | 开放贡献 |
| en_dict.json | 121,323 词 | 中英词典（翻译） | 开源词典 |
| en_completion.json | 303 词 | 英文自动补全 | 人工整理 |
| comma_pairs.json | 17,764 对 | 逗号句链补全 | 语料 |
| succession_extra.json | 189 键 | 顺承联想 | 人工+语料 |
| assoc_link.json | 308 键 | 关联联想 | 人工+语料 |
| ngram_link.json | 18,656 键 | N-gram 衔接 | 语料训练 |
| category_words*.json | 9,330 词 | 分类词库 | 人工整理 |
| daily_hot_words.json | 120 条 | 每日热词 | 每日自动抓取 |

## 端侧（assets/，≤100KB 门禁）
| 文件 | 规模 | 内容 |
|---|---|---|
| wubi_single.txt | 29KB | 字根字+一/二/三级简码+全码单字 |
| wubi_phrase.txt | 6.6KB | 仅 600 高频二字词 |

## 更新规则
- 新增词库：写生成脚本（gen_*.py，用 phrase_engine.phrase_to_code 按 86 构词公式）→ 输出 json → index.py 加 _load_code_words 加载 + code 接口 merge → 重建部署包 → 部署 → 抽样 50+ 验证 → 更新本文档
- 含英文/数字/标点/生僻字词：跳过（走拼音通道）
- 严禁繁体（云端全接口过滤 + 客户端渲染过滤）
