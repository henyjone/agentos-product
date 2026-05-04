import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from commit_guide.config_loader import get_default_model_config, load_config


class ConfigLoaderTest(unittest.TestCase):
    def test_load_config_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "models": {
                            "chat": {
                                "api_style": "openai-compatible",
                                "api_base": "https://example.com/v1/chat/completions",
                                "api_key": "sk-test",
                                "model": "test-model",
                            }
                        },
                        "default_chat_model": "chat",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(root)
            model = get_default_model_config(root)

        self.assertEqual(config["default_chat_model"], "chat")
        self.assertEqual(model["model"], "test-model")


if __name__ == "__main__":
    unittest.main()

