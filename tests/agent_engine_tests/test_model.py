import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_engine import ModelRequest, ModelResponse


class ModelSchemaTest(unittest.TestCase):
    def test_model_request_keeps_metadata(self) -> None:
        request = ModelRequest(
            prompt="生成管理简报",
            metadata={"mode": "management"},
        )
        response = ModelResponse(text="{}")

        self.assertEqual(request.metadata["mode"], "management")
        self.assertEqual(response.text, "{}")


if __name__ == "__main__":
    unittest.main()
