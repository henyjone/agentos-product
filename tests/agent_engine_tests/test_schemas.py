import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agent_engine.schemas import AnswerItem, SourceReference
from agent_engine.memory import MemoryScope


class SchemaTest(unittest.TestCase):
    def test_answer_item_references_source_id(self) -> None:
        source = SourceReference(
            id="project_status:pay-service:20260430",
            title="支付项目状态 - 2026-04-30",
            source_type="project",
            sensitivity="internal",
        )
        item = AnswerItem(
            content="支付项目最近 3 天没有新的验收记录。",
            source_id=source.id,
            confidence="high",
        )

        self.assertEqual(item.source_id, source.id)

    def test_memory_scope_values(self) -> None:
        self.assertEqual(
            {scope.value for scope in MemoryScope},
            {"personal", "team", "org", "restricted"},
        )


if __name__ == "__main__":
    unittest.main()
