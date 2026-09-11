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

### 3. 配置编码规则库（可选）
- 上传 `cloudwubi-rules/wubi86_basic.txt` 到函数所在目录
- 或设置 `CLOUDWUBI_RULES` 指向该文件
- 不配置则使用 `index.py` 内置默认字典（可跑通联调）

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

把端侧 `main.c` 中的网关地址改为你的函数 URL：
```c
#define GATEWAY_HOST "你的函数域名"
#define GATEWAY_PORT 443
#define GATEWAY_PATH "/release/wubi/query"
```

## 五、费用提示

- 云函数按调用量计费，日常个人使用几乎免费
- Redis 有免费额度/低费用档，可先用内存字典（不配 Redis）跑通
- 生产环境建议配置 Redis 缓存热点编码，降低查询成本

## 六、注意事项

1. 端侧仅上传编码，不上传完整输入原文，符合隐私设计
2. API 网关建议开启访问限流，防止恶意刷量
3. 生产环境建议启用 HTTPS（腾讯云 API 网关默认支持）
