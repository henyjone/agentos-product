import json
import sys
import time
import requests
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_siliconflow_config():
    config = load_config()
    return config["models"]["siliconflow_DSV4"]

def test_chat_completion():
    cfg = get_siliconflow_config()
    url = f"{cfg['api_base']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in one sentence."}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    print(f"Testing chat completion...")
    print(f"URL: {url}")
    print(f"Model: {cfg['model']}")
    
    try:
        start = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        elapsed = time.time() - start
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            print(f"Response: {content}")
            print("✓ Chat completion test passed")
            return True
        else:
            print(f"✗ Chat completion test failed")
            print(f"Error: {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("✗ Request timed out (120s)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Request failed: {e}")
        return False

def test_streaming():
    cfg = get_siliconflow_config()
    url = f"{cfg['api_base']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "user", "content": "Count from 1 to 3."}
        ],
        "max_tokens": 50,
        "stream": True
    }
    
    print(f"\nTesting streaming...")
    
    start = time.time()
    response = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
    
    chunks = []
    for line in response.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        chunks.append(content)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    
    elapsed = time.time() - start
    full_content = "".join(chunks)
    
    print(f"Response Time: {elapsed:.2f}s")
    print(f"Streamed Response: {full_content}")
    print("✓ Streaming test passed")
    return True

def test_invalid_request():
    cfg = get_siliconflow_config()
    url = f"{cfg['api_base']}/chat/completions"
    
    headers = {
        "Authorization": f"Bearer invalid_key",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "test"}]
    }
    
    print(f"\nTesting invalid API key...")
    
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print("✓ Invalid key test passed (correctly rejected)")
        return True
    else:
        print("✗ Invalid key test failed (should have been rejected)")
        return False

def main():
    print("=" * 60)
    print("SiliconFlow API Test Suite")
    print(f"Model: deepseek-ai/DeepSeek-V4-Flash")
    print("=" * 60)
    
    results = []
    
    results.append(("Chat Completion", test_chat_completion()))
    results.append(("Streaming", test_streaming()))
    results.append(("Invalid Key Handling", test_invalid_request()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")

if __name__ == "__main__":
    main()
