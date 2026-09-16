# brain-work 运行时 SSOT（多 Agent + 网关）

> 命中「brain-work / 网关 / 多 Agent / 记忆 / 验证怎么连」时读本文件。方法论仍见 `gateway.md` · `testmind.md` · `token-loading.md`。

## 1 部署（装一次）

| 组件 | 是什么 | 要装吗 |
|------|--------|--------|
| `BrainStackGateway` | FastAPI + `/mcp` + 控制台，`:18801` | **要**（Windows 服务或 `brain-gateway/start-gateway.ps1`） |
| `brainstack-memory` | stdio MCP，由网关懒启动 | **不要**单独给每个 Agent 配 |
| `brainstack-verify` | TestMind MCP（7 门面） | **不要**单独配 |
| `brainstack-token` | ContextMind MCP | **不要**单独配 |

数据根默认：`D:\shejiu-data\project-brain`（与 `servers.json` / 服务 env 一致）。

## 2 每个 Agent 只配一条

```json
{"mcpServers":{"brainstack-gateway":{"type":"http","url":"http://127.0.0.1:18801/mcp"}}}
```

仓库真源：`.cursor/mcp.json`（已收敛为仅 gateway）。

## 3 验证任务：精确工具链（禁整仓读）

TestMind 对外只有 **7 个门面**（`brain-verify/testmind/mcp.py` → `FACADES`），经网关前缀为 `brainstack-verify__<name>`。

典型顺序（按需跳步，不要一次 `tools/list` 全试）：

1. `analyze_impact` — 变更面 / 回归半径  
2. `plan_verification` — 契约与 case 计划  
3. `prepare_verification` — 环境 / seed  
4. `run_verification` — 执行  
5. `replay_failure` — 单 case 复现  
6. `final_gate` — 终判  
7. `cleanup` — 收尾  

**禁**：为「跑测试」通读 `brain-verify/` 或 `brain-work/`；先用 Grep/impact 门面，再读失败证据路径。

## 4 记忆任务

- 工具：`brainstack-memory__search_project_context`（参数 `project_id` + 具体 `query` + 小 `limit`）  
- 宿主原生探测已 **无 git**（仅本地 mtime），避免 stdio 子进程挂死（见 `HANDOFF_V3.md`）  
- 同参 60s 内网关读缓存命中 → 多 Agent 共享，勿重复刷后端  

## 5 并发与失败语义

- memory 读池默认 **4** 路；不同 query 并发高时出现 `BUSY` → 退避重试（设计内）  
- 就绪门未 READY → 快速失败提示预热，不等 300s  
- 审计：`GET /api/v2/gateway/audit/stats`（含 `by_error_code` · `cache_hits`）

## 6 阶段裁剪 `tools/list`（省 token）

- 配置：[`brain-gateway/config/gateway.json`](../../../brain-work/brain-gateway/config/gateway.json) 的 `tool_phase` / `phase_servers`
- HTTP MCP 请求头：`X-Brainstack-Phase: verification`（优先于配置）
- REST：`GET /api/v2/gateway/tools?phase=verification`
- `tools/call` 不受裁剪（全量索引仍可调用）

## 7 SkillMind 审计本仓 MCP 成本

在仓根执行：`python code-mind/skills/ai-skill-mcp-Y/scripts/skillmind.py audit --scope mcp`  
清单 SSOT：`code-mind/shared/mcp-registry.yaml`（standing 成本）。
