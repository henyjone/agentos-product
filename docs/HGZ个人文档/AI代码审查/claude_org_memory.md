代码审阅
总体评价
Phase 1 核心内核完成度高，代码质量不错。设计文档的核心数据模型基本落地，测试覆盖了关键路径，权限逻辑正确。

具体问题
1. MemoryStore 协议缺少 audit 方法

设计文档要求所有写入和删除都有 audit，interface.py 的 MemoryStore 协议里没有 audit 方法，但 InMemoryMemoryStore 里有实现。协议和实现不一致，后续对接 BackendMemoryStore 时容易漏掉。

store/interface.py:21 缺少：


def audit(self, action: str, target_type: str, target_id: str, actor_id: str, reason: str) -> None: ...
2. MemoryStore 协议缺少 apply_ingest_result

InMemoryMemoryStore 有 apply_ingest_result 这个便利方法，但协议里没有。测试里直接用了 InMemoryMemoryStore，没有通过协议调用，这没问题。但如果后续 pipeline 代码依赖这个方法，换成 BackendMemoryStore 时会出问题。建议要么加进协议，要么在 pipeline 层手动循环调用各个 upsert_*。

3. scope.py 中 manager 角色权限设计与文档不符

scope.py:42 里 manager 的 readable_scopes 包含了 SCOPE_PERSONAL，但设计文档明确说"管理者不能默认查看个人原始记忆"，测试 test_manager_cannot_read_other_personal_memory_by_default 也验证了这个行为。

实际上测试能通过是因为 can_read 里对 personal scope 有额外检查（owner_id 不匹配时拒绝），所以行为是对的，但 readable_scopes 里包含 personal 会让人误解这个角色的权限边界。建议把 manager 的 readable_scopes 改为 (SCOPE_TEAM, SCOPE_ORG)，让权限规则本身就能表达意图，不依赖后续的 owner_id 检查来纠正。

4. _confidence_for_commit_event 逻辑顺序问题

fact_extractor.py:155：


if event.payload.get("patch_excerpt") or event.payload.get("file_snapshots") or event.payload.get("has_patch"):
    return CONFIDENCE_HIGH
if event.payload.get("files") or event.payload.get("staged_files"):
    return CONFIDENCE_MEDIUM
if event.payload.get("message") or event.payload.get("commit_message"):
    return CONFIDENCE_MEDIUM
第二和第三个分支都返回 CONFIDENCE_MEDIUM，可以合并。另外，commit_guide_submit 事件的 diff_context 字段没有被检查，但它是判断是否有 patch 的关键字段（has_patch 是从 diff_context 派生的，但如果调用方没传 has_patch 只传了 diff_context，这里会漏判）。

5. 缺少 project_docs ingest

设计文档 Phase 1 验收要求能把项目文档（项目背景.md、项目进度.md、项目目的.md）纳入组织记忆，但 ingest/project_docs.py 没有实现。RuleFactExtractor 里有 _project_doc_fact 处理 project_doc_update 事件，但没有对应的 ingestor 来产生这类事件。

6. InMemoryMemoryStore 不是 Phase 1 计划的存储

设计文档 Phase 1 要求实现 LocalSQLiteMemoryStore，但实现的是 InMemoryMemoryStore。内存存储进程退出后数据丢失，无法支持"再运行一次日报时，系统知道之前的总结和事实"这个 Phase 2 验收标准。如果这是有意为先，需要明确。

做得好的地方
frozen=True dataclass 保证了数据不可变，正确
_dedupe_entities 防止重复实体写入
_confidence_for_commit_event 正确实现了设计文档的置信度规则
权限过滤在 store 层做，不是在 agent 层做，架构正确
测试用 FakeModel 隔离 AI 依赖，测试可靠
优先级建议
优先级	问题
高	LocalSQLiteMemoryStore（数据持久化，Phase 2 前必须）
高	project_docs ingestor（Phase 1 验收要求）
中	MemoryStore 协议补 audit 方法
低	manager 角色 readable_scopes 语义修正
低	_confidence_for_commit_event 合并冗余分支