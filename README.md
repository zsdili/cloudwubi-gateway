# CloudWubi Gateway — 云端网关

> 面向 5G/6G 的云原生五笔输入法 · 云端组件
> 腾讯云函数 · 编码查询 + 动态构词 · Redis 热点缓存

## 简介

CloudWubi Gateway 是 CloudWubi 云五笔输入法的**云端大脑入口**。
接收端侧客户端上传的五笔编码，查询云端编码库、动态生成词组，
返回候选汉字 Unicode 码点。核心算力全部在云端，端侧保持 <800KB 极简。

## 功能

| 版本 | 功能 | 状态 |
| ---- | ---- | ---- |
| 阶段1 | 编码查表（内存字典 + Redis 热点缓存） | ✅ 完成 |
| 阶段2 | **五笔动态构词引擎（无限组词）** | ✅ 本版本 |
| 阶段3 | 语义排序、场景权重、联邦自学习 | 📋 规划 |

## 架构

```
端侧客户端 (cloudwubi-client)
    ↓ POST {"code":"wqvb","phrase":true}
本仓库 (index.py)
  1. 编码合法性校验
  2. Redis 热点缓存查询（微秒级）
  3. 云端五笔编码库查表
  4. 动态构词引擎生成词组（阶段2）
    ↓ 返回 Unicode 码点数组
端侧渲染汉字
```

## 快速开始

```bash
# 本地测试网关
python3 index.py
# 期望输出：{"code":"wq","candidates":[20320]}

# 单元测试
python3 test_phrase_engine.py
```

## API 接口

### POST 单字查询

```json
请求：{"code": "wq"}
响应：{"code": "wq", "candidates": [20320]}
```

### POST 动态构词查询

```json
请求：{"code": "wqvb", "phrase": true}
响应：{"code": "wqvb", "candidates": [20320, 22909], "phrases": ["你好"]}
```

### 错误响应

```json
{"error": "invalid code, expect 1-4 of a-y"}
```

## 动态构词原理（核心）

五笔词组**无需预先存储**，只要掌握单字编码 + 构词公式即可动态生成：

| 词型 | 公式 | 示例 |
| ---- | ---- | ---- |
| 二字词 | 第1字前2码 + 第2字前2码 | 你(wq)+好(vb) → wqvb |
| 三字词 | 首码+首码+前2码 | 人(w)+民(n)+共(aw) → wnaw |
| 四字+ | 首+首+首+末首 | 中(kl)国(lg)人(w)民(n) → klwn |

实现见 `phrase_engine.py`，含**反向校验**（词组 → 编码，供规则库 CI 使用）。

## 部署到腾讯云

完整部署步骤见 [DEPLOY.md](DEPLOY.md)：
1. 创建云函数（Python 3.9+）
2. 配置 API 网关触发器（POST + CORS）
3. 可选：配置 Redis 环境变量（REDIS_HOST/PORT/PASSWORD）
4. 可选：上传 `wubi86_basic.txt` 规则文件（CLOUDWUBI_RULES）

## 依赖

- 基础功能：零第三方库（纯标准库）
- Redis 缓存：可选安装 `redis`（见 requirements.txt）

## 设计原则

1. **高效**：Redis 热点缓存微秒响应，冷编码才走字典/AI
2. **可扩展**：模块解耦，阶段3 语义排序直接接入响应管线
3. **可持续**：无状态云函数，弹性伸缩，按量计费
4. **兼容**：旧接口（阶段1）完全向后兼容

## 许可

MIT License · 贡献规范见 [CONTRIBUTING.md](CONTRIBUTING.md)

## 相关仓库

- [cloudwubi-client](https://github.com/zsdili/cloudwubi-client) - 端侧内核
- [cloudwubi-rules](https://github.com/zsdili/cloudwubi-rules) - 五笔规则库（去中心化共建）
- [cloudwubi-ai](https://github.com/zsdili/cloudwubi-ai) - AI 引擎（规划中）
