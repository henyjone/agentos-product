  ✦ 测试全部通过（10/10）。下面是审阅结果。

    ---

    代码审阅

    总体评价：代码质量好，核心结构清晰。6 个实际问题，3 个建议。

    ---

    🔴 问题

    1. `AIFactExtractor` 没有校验 AI 输出的数据约束

    _fact_from_dict 盲目接受 AI 输出的任何值。设计方案 §15.1 规定"AI 不允许生成没有 source_ids 的 high confidence fact"，但代码里没有校验：

     1 # fact_extractor.py: _fact_from_dict
     2 confidence=str(item.get("confidence") or CONFIDENCE_LOW)  # 直接接受
     3 source_ids=[str(value) for value in item.get("source_ids", []) if str(value)]

    AI 输出 {"confidence":"high", "source_ids":[]} 时静默通过。建议加：

     1 confidence = str(item.get("confidence") or CONFIDENCE_LOW)
     2 if confidence == CONFIDENCE_HIGH and not source_ids:
     3     confidence = CONFIDENCE_MEDIUM  # 降级

    2. `InMemoryMemoryStore.get_source()` 不存在时抛 KeyError

    MemoryStore Protocol 签名返回 Source（暗示可能为 None），但实现直接 self.sources[source_id]，不存在就炸。search_facts 的调用方如果要根据 fact.source_ids 去查 source，会意外崩溃。建议加
    `self.sources.get(source_id)`。

    3. `ids.py` 的 `:` 分隔符存在语义冲突

    safe_id 把 / 转成 :，但 : 也是 entity_id("type", "value") 的分隔符。结果是：

     1 entity_id("repo", "HGZ/agentos-product")
     2 # → "repo:HGZ:agentos-product"  # 三段，预期两段

    当前代码依靠这个行为工作，但如果后续要反向解析 ID（id.split(":", 1)），会出错。建议把 safe_id 里的 / 替换为 - 或保持 / 直接允许。

    4. `ingest/gitea.py` 的 `_commit_actor()` 兜底为 "unknown"

    当 Gitea API 不返回 author 信息时，所有未知提交者都汇入 person:unknown。这会导致多个人的工作被合并到同一个 entity。建议至少用 commit email 或在无信息时记录为 person:anonymous_{sha[:8]}。

    5. `scope.py` 中 `filter_readable` 未传 `team_id`

      1 # scope.py line 112
      2 def filter_readable(self, context, items):
      3     for item in items:
      4         if self.can_read(
      5             context=context,
      6             scope=getattr(item, "scope", ...),
      7             sensitivity=getattr(item, "sensitivity", ...),
      8             owner_id=getattr(item, "subject_entity_id", None),
      9             project_id=getattr(item, "project_id", None),
     10             # team_id 缺失 — 永远为 None
     11         ):

    AccessContext 有 team_ids 字段但 filter_readable 没有从 item 上取 team_id 传入 can_read。

    6. `commit_guide` 和 `repo_analyzer` 没有 `--write-memory` 接入

    org_memory/ingest/ 的构建器已经在测试中可以独立运行，但 src/commit_guide/main.py 和 src/repo_analyzer/main.py 没有任何调用。org_memory 目前是"库已就绪，CLI 未接入"状态。

    ---

    🟡 建议

    7. 添加 FactComparator（双线验证）

    Rule 和 AI 两条路线都有了，但缺少比较层。建议加一个 compare_extraction_results(rule_result, ai_result) → ComparisonReport，提供一致性率统计。可以放在 Phase 2，但现在把接口预留出来。

    8. AI extractor 的错误处理

    _parse_json 在 AI 返回非法 JSON 时会抛异常，但 AIFactExtractor.extract() 没有 try/except。AI 偶尔会输出非 JSON 或格式错误，应该捕获并返回空 ExtractionResult + 记录错误，而不是让整个 pipeline 崩溃。

    9. 测试缺口

    当前 10 个测试覆盖质量不错，但缺几个关键场景：
     - get_source 不存在的 source_id → KeyError（会暴露问题 2）
     - search_facts 的 time_from/time_to 过滤（MemoryQuery 有字段但 store 没实现过滤）
     - AI 返回 confidence=high 但 source_ids=[] 的降级行为（会暴露问题 1）

    ---

  ╭───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
  │ ✓  TodoWrite Update todos                                                                                                                                                                                 │
  │                                                                                                                                                                                                           │
  │    ●  审查 org_memory 核心代码（domain, scope, ids, extraction）                                                                                                                                          │
  │    ●  审查 store 层（interface + in_memory 实现）                                                                                                                                                         │
  │    ●  审查 ingest 层（commit_guide + gitea）                                                                                                                                                              │
  │    ●  审查测试覆盖                                                                                                                                                                                        │
  │    ●  汇总问题清单                                                                                                                                                                                        │
  ╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

  ✦ Review is complete. All 10 tests pass. I've identified 6 concrete issues and 3 suggestions. The user can now decide what to fix first.

  ✦ 审阅完成。6 个实际问题中，问题 1、2、3 是运行时会出错的，问题 4、5、6 是功能缺口。需要我修复哪些？