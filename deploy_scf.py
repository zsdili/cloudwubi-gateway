#!/usr/bin/env python3
"""CloudWubi 网关一键部署：腾讯云 SCF UpdateFunctionCode（TC3-HMAC-SHA256 签名）"""
import base64, hashlib, hmac, json, os, sys, datetime

SECRET_ID = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TENCENT_SECRET_ID", "")
SECRET_KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TENCENT_SECRET_KEY", "")
if not SECRET_ID or not SECRET_KEY:
    sys.exit("用法: python3 deploy_scf.py <SecretId> <SecretKey>")

def sign_request(secret_id, secret_key, service, host, action, version, region, payload, method="POST"):
    t = datetime.datetime.now(datetime.timezone.utc)
    date = t.strftime("%Y-%m-%d")
    timestamp = str(int(t.timestamp()))
    ct = "application/json; charset=utf-8"
    # 1. 拼接规范请求串
    canonical_headers = "content-type:%s\nhost:%s\n" % (ct, host)
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join([method, "/", "", canonical_headers, signed_headers, hashed_payload])
    # 2. 拼接待签名字符串
    credential_scope = "%s/%s/tc3_request" % (date, service)
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join(["TC3-HMAC-SHA256", timestamp, credential_scope, hashed_canonical])
    # 3. 计算签名
    def hmac_sha256(key, msg): return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    k_date = hmac_sha256(("TC3" + secret_key).encode("utf-8"), date)
    k_service = hmac_sha256(k_date, service)
    k_signing = hmac_sha256(k_service, "tc3_request")
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    # 4. 拼接 Authorization
    authorization = "TC3-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (
        secret_id, credential_scope, signed_headers, signature)
    headers = {
        "Authorization": authorization,
        "Content-Type": ct,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": timestamp,
        "X-TC-Version": version,
        "X-TC-Region": region,
    }
    return headers

host = "scf.tencentcloudapi.com"
service = "scf"
version = "2018-04-16"
region = "ap-guangzhou"
# v0.5.47 修复：支持命令行第 3 参数指定 zip（否则用固定路径）
zipfile_path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloudwubi-gateway-scf.zip")
zip_b64 = base64.b64encode(open(zipfile_path, "rb").read()).decode("ascii")
payload = json.dumps({
    "FunctionName": "cloudwubi-gateway",
    "Handler": "index.main_handler",
    "ZipFile": zip_b64,
})
headers = sign_request(SECRET_ID, SECRET_KEY, service, host, "UpdateFunctionCode", version, region, payload)
import urllib.request
req = urllib.request.Request("https://" + host + "/", data=payload.encode("utf-8"), headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read().decode("utf-8")
        d = json.loads(body)
        if "Response" in d and d["Response"].get("Error"):
            print("部署失败:", d["Response"]["Error"])
            sys.exit(1)
        print("✅ 部署成功: RequestId=%s" % d.get("Response", {}).get("RequestId", "?"))
except urllib.error.HTTPError as e:
    print("HTTP %s: %s" % (e.code, e.read().decode("utf-8", errors="replace")[:500]))
    sys.exit(1)

# v0.6.x：设置函数环境变量（TMT 机器翻译兜底 Key 存 SCF 环境变量，不落代码/仓库）
import time as _time
_time.sleep(25)  # 等 UpdateFunctionCode 完成后函数不再处于 Updating 状态
_env_payload = json.dumps({
    "FunctionName": "cloudwubi-gateway",
    "Timeout": 30,   # v0.6.8：冷启动加载 8MB 词库+12万词典需 >3s，默认 3s 超时导致 en/words 接口间歇失败
    "Environment": {"Variables": [
        {"Key": "TMT_SECRET_ID", "Value": SECRET_ID},
        {"Key": "TMT_SECRET_KEY", "Value": SECRET_KEY},
        {"Key": "BAIDU_APPID", "Value": sys.argv[4] if len(sys.argv) > 4 else ""},
        {"Key": "BAIDU_KEY", "Value": sys.argv[5] if len(sys.argv) > 5 else ""},
    ]},
})
_env_headers = sign_request(SECRET_ID, SECRET_KEY, service, host, "UpdateFunctionConfiguration", version, region, _env_payload)
_env_req = urllib.request.Request("https://" + host + "/", data=_env_payload.encode("utf-8"), headers=_env_headers, method="POST")
try:
    with urllib.request.urlopen(_env_req, timeout=120) as r:
        _d = json.loads(r.read().decode("utf-8"))
        if "Response" in _d and _d["Response"].get("Error"):
            print("环境变量设置失败:", _d["Response"]["Error"])
        else:
            print("✅ 环境变量已设置: TMT_SECRET_ID/TMT_SECRET_KEY")
except urllib.error.HTTPError as e:
    print("环境变量设置 HTTP %s: %s" % (e.code, e.read().decode("utf-8", errors="replace")[:400]))

# v0.6.11 部署即验证：部署后自动 curl 抽样验证（2-3 个接口），失败即报错（防"SCF 旧容器/数据不生效"）
import urllib.parse as _up
try:
    _GATEWAY = "https://1251037126-bglnivgmaf.ap-guangzhou.tencentscf.com"
    _checks = [("code", {"code": "lyab", "phrase": True}, "国庆节"),
               ("code", {"code": "qkhh", "phrase": True}, "钟"),
               ("context", {"context": "床前明月光"}, None)]
    _ok = 0
    for _itf, _body, _expect in _checks:
        try:
            _req = urllib.request.Request(_GATEWAY, data=json.dumps(_body).encode("utf-8"),
                                          headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(_req, timeout=60) as _r:
                _resp = json.loads(_r.read().decode("utf-8"))
                _txt = json.dumps(_resp, ensure_ascii=False)[:200]
                if _expect and _expect not in _txt:
                    print("⚠️ 部署后验证未过: %s 缺 %s → %s" % (_itf, _expect, _txt))
                else:
                    print("✅ 部署后验证通过: %s → %s" % (_itf, _txt[:80]))
                    _ok += 1
        except Exception as _e:
            print("⚠️ 部署后验证异常 %s: %s" % (_itf, _e))
    if _ok < 2:
        print("❌ 部署后验证不足（仅 %d/3 通过），请检查 SCF 是否真正更新" % _ok)
except Exception as _e:
    print("部署后验证脚本异常（不影响部署）: %s" % _e)
