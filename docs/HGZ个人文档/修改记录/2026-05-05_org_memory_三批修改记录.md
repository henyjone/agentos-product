# 2026-05-05 组织记忆三批修改记录

## 第一批：核心可靠性修复

1. `src/org_memory/domain.py`
   - 增加 `VALID_SCOPES`、`VALID_SENSITIVITIES`、`VALID_CONFIDENCES`。
   - `ExtractionResult` 增加 `errors`，AI 提取失败时不再直接中断流程。

2. `src/org_memory/ids.py`
   - 修复 ID 段内部继续使用 `:` 的问题，避免和顶层结构分隔符冲突。
   - 非 ASCII 值不再退化为 `unknown`，改为稳定 hash，避免中文用户名被合并。

3. `src/org_memory/scope.py`
   - `AccessRule` 增加 `personal_access`，默认 `own_only`。
   - 管理者仍可读自己的私人记忆，但不能默认读取其他员工私人记忆。

4. `src/org_memory/extraction/fact_extractor.py`
   - AI JSON 解析失败、模型异常、非法 item 不再崩溃，统一进入 `ExtractionResult.errors`。
   - AI 产出的 fact 如果缺少 `source_ids`，会降为 `low` 且标记为 `needs_review`。
   - 非法 `confidence/scope/sensitivity` 会回落到安全默认值。
   - `diff_context` 被视为代码证据，可支持 high confidence。

5. `src/org_memory/store/interface.py`、`src/org_memory/store/in_memory.py`
   - `MemoryStore` 协议补充 `apply_ingest_result` 和 `audit`。
   - `get_source()` 缺失时返回 `None`，不再抛出 `KeyError`。
   - 查询补充 `time_from/time_to` 和 `source_types` 过滤。

6. `src/org_memory/ingest/gitea.py`
   - Gitea 提交作者未知时使用 `anonymous_<sha8>`，不再合并到 `person:unknown`。
   - commit event payload 增加 `diff_context`。

## 第二批：存储和项目上下文摄取

1. `src/org_memory/store/local_sqlite.py`
   - 新增本地 SQLite 记忆库，支持实体、来源、事件、事实、关系、审计记录持久化。

2. `src/org_memory/store/utils.py`
   - 新增统一 `apply_ingest_result()`，避免不同入口重复写入逻辑。

3. `src/org_memory/ingest/project_docs.py`
   - 新增项目文档摄取器，优先读取：
     - `项目背景.md`
     - `项目进度.md`
     - `项目目的.md`
     - `README.md`

4. `src/org_memory/ingest/gitea.py`
   - Gitea 扫描结果里的 `project_context` 也会转换为 `project_doc_update` 事件。

5. `src/org_memory/__init__.py`、`src/org_memory/store/__init__.py`、`src/org_memory/ingest/__init__.py`
   - 导出新增存储和摄取能力。

## 第三批：接入现有工具入口

1. `src/repo_analyzer/main.py`
   - 增加 `--write-memory` 和 `--memory-db`。
   - `--all-repos`、单仓库日报、`--detail` 详细扫描都可把扫描证据写入组织记忆。
   - 默认数据库路径：`D:\pro\agentos-product\data\org_memory.sqlite`。

2. `src/commit_guide/main.py`
   - 增加 `--write-memory` 和 `--memory-db`。
   - commit 成功后会把本次提交、暂存文件、diff 上下文、提交信息写入组织记忆。
   - 原有提交流程不变，只有显式加 `--write-memory` 才落库。

## 新增和补充测试

1. `tests/org_memory_tests/test_fact_extractor.py`
   - 覆盖规则提取、`diff_context` 证据、AI 输出校验、无效 JSON 错误返回。

2. `tests/org_memory_tests/test_ingest_and_store.py`
   - 覆盖 Gitea 摄取、commit-guide 摄取、权限过滤、时间过滤、SQLite 持久化、项目文档摄取、未知作者兜底。

3. `tests/org_memory_tests/test_scope.py`
   - 覆盖 manager 读取自己私人记忆与拒绝读取他人私人记忆。

4. `tests/org_memory_tests/test_ids.py`
   - 覆盖 ID 分隔符和中文值 hash。

## 验证结果

1. `python -m unittest discover -s tests\org_memory_tests -p "test*.py"`
   - 21 tests passed.

2. `python -m unittest discover -s tests -p "test*.py"`
   - 95 tests passed.

## 当前使用方式

1. 管理者日报写入组织记忆：

```powershell
python -m repo_analyzer.main --all-repos --days 1 --write-memory --output reports\gitea-daily.md
```

2. 指定 SQLite 路径：

```powershell
python -m repo_analyzer.main --all-repos --days 1 --write-memory --memory-db data\org_memory.sqlite
```

3. 提交工具写入组织记忆：

```powershell
python -m commit_guide.main --push --write-memory
```

## 说明

本次只把组织记忆落库做成显式开关，没有改变现有日报和提交工具的默认行为。当前写入记忆时使用规则提取器，保证测试稳定；AI 事实提取通道已经加了校验和错误返回，可以在后续 Agent 编排阶段再接入。
