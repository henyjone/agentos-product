import json
import sys
import time
from pathlib import Path

import requests


CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
DEFAULT_MODEL_ALIAS = "deepseek-V4-pro"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_model_config(alias=DEFAULT_MODEL_ALIAS):
    config = load_config()
    return config["models"][alias]


def test_endpoint(name, cfg):
    url = cfg["api_base"]

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
    }

    print(f"\n{'=' * 50}")
    print(f"Testing: {name}")
    print(f"URL: {url}")
    print(f"Model: {cfg['model']}")
    print(f"{'=' * 50}")

    try:
        start = time.time()
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        elapsed = time.time() - start

        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {elapsed:.2f}s")
        print(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            data = response.json()
            print(f"Response: {data}")
            print("SUCCESS")
        else:
            print(f"Error Response: {response.text}")
            print("FAILED")

    except requests.exceptions.Timeout:
        print("TIMEOUT - Request timed out after 30s")
    except requests.exceptions.ConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
    except requests.exceptions.RequestException as e:
        print(f"REQUEST ERROR: {e}")


if __name__ == "__main__":
    alias = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_ALIAS
    test_endpoint(alias, get_model_config(alias))
