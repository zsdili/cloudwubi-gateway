# CloudWubi 云端网关部署说明（腾讯云函数）

本文件说明如何把 `index.py` 部署到腾讯云函数，实现端到端查询链路。

## 一、部署前准备

1. 注册腾讯云账号：https://cloud.tencent.com
2. 开通「云函数 SCF」服务（新用户通常有免费额度）
3. 可选：开通「云数据库 Redis」，用于热点缓存加速

## 二、部署步骤（控制台方式，无需命令行）

### 1. 创建云函数
1. 登录腾讯云控制台 → 搜索「云函数」→ 进入 SCF
2. 点击「新建」→ 选择「从头开始」
3. 配置：
   - 函数名称：`cloudwubi-gateway`
   - 运行环境：Python 3.9 或更高
   - 创建方式：在线编辑
4. 把本目录 `index.py` 的全部内容复制到代码编辑框
5. 若启用 Redis，添加环境变量：
   - `REDIS_HOST`：Redis 内网地址
   - `REDIS_PORT`：默认 6379
   - `REDIS_PASSWORD`：Redis 密码
   - `CLOUDWUBI_RULES`：编码库文件路径（默认 `wubi86_basic.txt`）
6. 点击「完成」

### 2. 配置 API 网关触发器
1. 在函数详情 →「触发管理」→「创建触发器」
2. 触发器类型：API 网关触发
3. 请求方法：POST
4. 启用 CORS（跨域），方便端侧调用
5. 保存后，会生成一个访问 URL，形如：
   `https://service-xxx.ap-guangzhou.apigateway.myqcloud.com/release/wubi/query`

### 方法B（推荐）：zip 部署包一键上传

已为您打好完整部署包 `cloudwubi-gateway-scf.zip`（含 index.py + phrase_engine.py + semantic_ranker.py + 词库 wubi86_basic.txt + wubi86_phrases.txt + requirements.txt，约 555KB，SCF 个人高级版 0 元额度内）：

1. 登录腾讯云控制台 → 搜索「云函数」→ 进入 SCF：https://console.cloud.tencent.com/scf
2. 点「新建」→「从头开始」→「本地上传 zip 包」
3. 上传 `cloudwubi-gateway-scf.zip`
4. 运行环境：Python 3.9；函数名称：`cloudwubi-gateway`；执行方法：`index.main_handler`
5. 内存：256MB（套餐默认）；超时时间：5 秒
6. 创建完成后 →「触发管理」→「创建触发器」→ API 网关触发（POST，启用 CORS）
7. 记录生成的访问 URL（形如 `https://service-xxx.ap-guangzhou.apigateway.myqcloud.com/release/wubi/query`）

## 三、测试

### 本地测试网关
```bash
cd cloudwubi-gateway
python index.py
# 期望输出：
# {'statusCode': 200, ..., 'body': '{"code": "wq", "candidates": [20320]}'}
```

### 用 curl 测试云端接口
```bash
curl -X POST https://你的函数地址/release/wubi/query \
  -H "Content-Type: application/json" \
  -d '{"code":"wq"}'
# 期望返回：
# {"code":"wq","candidates":[20320]}   # 20320 = 你
```

## 四、端侧对接

把端侧 Android `CloudWubiIME.java` 顶部的网关地址改为你的函数 URL：
```java
private static final String GATEWAY_URL =
        "https://你的函数域名/release/wubi/query";
```
改后推送 main，CI 自动构建新 APK；未部署前保持占位符（端侧自动跳过云端请求，离线词库正常可用）。

## 五、费用提示

- 云函数按调用量计费，日常个人使用几乎免费
- Redis 有免费额度/低费用档，可先用内存字典（不配 Redis）跑通
- 生产环境建议配置 Redis 缓存热点编码，降低查询成本

## 六、注意事项

1. 端侧仅上传编码，不上传完整输入原文，符合隐私设计
2. API 网关建议开启访问限流，防止恶意刷量
3. 生产环境建议启用 HTTPS（腾讯云 API 网关默认支持）
