import requests
import json
import time

api_key = "sk-ltiejtnslydnvaujlbdbadssacfqawghayrbgoefosyslahz"
base_url = "https://api.siliconflow.cn/v1"

print("Test 1: GET /v1/models")
try:
    r = requests.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
    print(f"  Status: {r.status_code}")
    print(f"  OK: {r.status_code == 200}")
except Exception as e:
    print(f"  Error: {e}")

print("\nTest 2: POST with different content types")

payload = {
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "messages": [{"role": "user", "content": "hi"}],
    "max_tokens": 10
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

for timeout_val in [5, 10, 15]:
    print(f"\n  Timeout: {timeout_val}s")
    try:
        start = time.time()
        r = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=timeout_val)
        elapsed = time.time() - start
        print(f"  Status: {r.status_code}, Time: {elapsed:.2f}s")
        print(f"  Response: {r.text[:300]}")
    except requests.exceptions.Timeout:
        print(f"  TIMEOUT after {timeout_val}s")
    except Exception as e:
        print(f"  Error: {e}")

print("\nTest 3: Try with session and keep-alive")
session = requests.Session()
session.headers.update(headers)
try:
    start = time.time()
    r = session.post(f"{base_url}/chat/completions", json=payload, timeout=15)
    elapsed = time.time() - start
    print(f"  Status: {r.status_code}, Time: {elapsed:.2f}s")
    print(f"  Response: {r.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")
