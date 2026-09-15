<!-- ref-index -->
# api-wire · 本仓接口 wire 实测表（**探测记录，不是规范定义**）

**性质**：本表是**本仓现状的抄录**，不是「应该长什么样」的规定。本 skill 不给任何默认值。
**铁律**：每行必须有 `证据=文件:行`；填不出证据 = 没探测，**留空**，禁填想当然的值。
**用法**：复制到 `domain-packs/<proj>/api-wire.md`；先跑「采集」，再把实测结果抄进表。
**消费方**：`ai-code` → `references/contract.md`（第一步探测 / 第二步抄 / 三不改 / breaking 出口）。

## 现实差异样本（**证明没有默认值**；仅供识别，禁当规范）

同一概念在不同仓里的真实写法，每一行都合法、互不通用：

| 概念 | 见过的写法（择一，不是选项清单） |
|------|--------------------------------|
| 分页返回 | `{rows,total}` / `{records,total}` / `{list,total,pageNum,pageSize}` / `{data:{list,total}}` / `{items,totalCount}` |
| 分页入参 | `pageNum/pageSize` / `page/size` / `current/size` / `pageNo/pageSize` / `offset/limit` |
| 排序 | `orderByColumn/isAsc` / `orderBy/asc` / `sortField/sortOrder` / `sortBy/order` / `sidx/sord` |
| 包装 | `{code,msg,data}` / `{code,data,message}` / `{success,result,errorCode}` / `{status,payload}` / 裸对象 |
| 状态字段 | `status` / `state` / `auditStatus` / `checkStatus` / `statusCode` / `flowStatus` |
| 布尔 | `1/0` / `true/false` / `"Y"/"N"` / `"0"/"1"` |
| 时间 | `yyyy-MM-dd HH:mm:ss` / 秒级时间戳 / 毫秒时间戳 / ISO8601 |
| 多选 | 逗号串 / 分号串 / JSON 数组 / 重复 query 参 |
| 空列表 | `[]` / `null` / `rows:[]` |

**上表每一行都不是默认值。** 你要改的仓用哪个，就一直是哪个；换一个 = breaking。
仓内同时存在多种（新接口 `{code,msg,data}`、旧接口 `{success,result}`）是**常态，不是缺陷**。

## 采集（禁凭经验；结果直接抄进下面各表）

| 目标 | 命令（按仓调整路径） |
|------|----------------------|
| 响应包装类 | `grep -rn "class R\b\|class AjaxResult\|class Result\|class Resp\|ResponseEntity" --include=*.java .` |
| 分页包装类 | `grep -rn "class TableDataInfo\|class PageResult\|class PageVO\|IPage\|PageInfo" --include=*.java .` |
| 分页入参 | `grep -rn "class PageDomain\|pageNum\|pageSize\|pageNo\|current\|offset" --include=*.java .` |
| Controller 入参 | `grep -rhn "@RequestParam\|@PathVariable" --include=*Controller.java .` |
| 返回类型分布 | `grep -rn "public .*\(R<\|AjaxResult\|TableDataInfo\|Result\)" --include=*Controller.java .` |
| VO 状态字段 | `grep -rn "private .*[Ss]tatus\|private .*[Ss]tate\|private .*[Tt]ime\|private .*[Ff]lag" --include=*.java --include=*.xml .` |
| 前端消费 | `grep -rn "\.rows\|\.records\|\.total\b\|res\.data\.\|queryParams\." --include=*.vue --include=*.js src` |

## 1. 包装（**允许并存多套**；逐行抄实测，别合并）

| 用途 | 实测类 | wire 结构 | 证据 文件:行 | 覆盖范围 |
|------|--------|-----------|--------------|----------|
| 列表/分页 | | | | |
| 单对象 | | | | |
| 单对象（另一套） | | | | |
| 空结果语义 | | | | |

> 并存是常态，**不要**在这一步顺手统一。改哪个接口就跟哪一套。

## 2. 分页入参（GET/列表）

| 概念 | 实测参名 | 类型 | 默认值 | 证据 文件:行 |
|------|----------|------|--------|--------------|
| 页码 | | | | |
| 每页条数 | | | | |
| 排序字段 | | | | |
| 排序方向 | | | | |
| 时间范围-起 | | | | |
| 时间范围-止 | | | | |
| 多选 | | | | |

## 3. 状态族（一个业务状态一个名；抄实测，禁自造）

| 业务状态 | 实测 wire 名 | 类型 | 值域 | 已出现接口 | 证据 文件:行 |
|---|---|---|---|---|---|
| | | | | | |

## 4. 枚举与类型形态（跟本仓，不跟模板）

| 项 | 本仓实测形态 | 本仓是否已混用 | 证据 文件:行 |
|----|--------------|----------------|--------------|
| 状态返回 | | | |
| 布尔 | | | |
| 时间 | | | |
| 金额 | | | |
| 多选分隔 | | | |

## 5. 前端消费点（改 wire 前必查这里）

| wire 字段 | 前端消费位置 | 证据 文件:行 |
|-----------|--------------|--------------|
| | | |

> 这张表就是 breaking 的影响面清单。改某字段前先数它下面有几行。

## 6. 变更记录（breaking 必留痕）

格式：`日期 | 接口 | 字段 | 旧 → 新 | breaking/additive | 前端改动点 | 确认人`

| 日期 | 接口 | 字段 | 旧 → 新 | 类型 | 前端改动点 | 确认 |
|---|---|---|---|---|---|---|
| | | | | | | |

## 路由

改接口 → `contract.md`（先探测，再照抄，三不改，breaking 走出口）。
additive：本表 1-4 节补行即可，无需用户确认。
改名/删字段/换语义/换包装：`contracts_changed=yes` + breaking 表 + 用户确认。
全仓统一（跨套收敛）：独立任务，走 `/ai-design`，禁搭本次需求的车。
