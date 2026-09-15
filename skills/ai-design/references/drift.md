# drift · Diagram Drift 检测

**问题**：代码一直在变，图不动 → 图变成谎言 → 比没有图更糟。

## 检测什么

| 漂移类型 | 判据 | 严重度 |
|---------|------|--------|
| 新增未画 | 代码出现新模块/服务/类，图里没有 | HIGH |
| 删除未清 | 图里有节点，代码已删 | MEDIUM |
| 改名未同步 | 图节点名与代码类名不符 | MEDIUM |
| 边缺失 | 图缺调用/依赖边 | LOW |

## 用法

```bash
node scripts/drift.mjs <项目根> docs/diagram            # 默认：只查架构级组件
node scripts/drift.mjs <项目根> docs/diagram --all      # 含 scripts/tools 等工具目录
node scripts/drift.mjs <项目根> docs/diagram --json     # 机器可读
```

## 降噪设计（重要）

裸比对会把「用户/接入层」这类概念节点判成"已删"，全是假阳性。本脚本三层降噪：

| 层 | 规则 | 作用 |
|----|------|------|
| 代码侧 | 只收**组件式命名**（`*Service`/`*Agent`/`*Mind`/`*Handler`…） | 工具脚本不算架构漂移 |
| 代码侧 | 默认跳过 `scripts/ tools/ bin/ migrations/` | `--all` 可纳入 |
| 图侧 | STALE **只认 ASCII 组件式标签**（中文/概念节点不参与） | 消灭"用户/接入层已删"假阳性 |

自定义：项目根放 `.diagramdrift.json`

```json
{ "ignore": ["src/legacy/**"], "include": ["src/modules/**"] }
```
`include` 非空时，只查 include 命中的文件。

## 节点命名约定（否则 drift 测不准）

**图节点 ID / 标签应能对应代码模块名**：

```d2
pay_svc: PaymentService { }   # ✅ 能对上 PaymentService.java
pay: 支付 { }                  # ⚠️ 对不上，drift 会误报
```

中文显示名可以留，但建议保留英文组件名（`pay_svc: 支付服务 PaymentService`）。

## 算法

1. **扫描代码**：按语言 glob 抽模块名
   - Java: `**/src/main/java/**/*.java` → 类名（去 `Service`/`Impl` 后缀做归一）
   - TS/JS: `**/src/**/*.{ts,tsx,js,mjs}` → 导出名
   - Python: `**/*.py` → 顶层 class/def
2. **扫描图**：从 `docs/diagram/*.md` 的 DSL 里抽节点显示名
3. **归一比对**：模糊匹配（小写 + 去后缀 + 去分隔符）
4. **输出**：
   - 代码有、图没有 → `DRIFT: 新增 <名>`（HIGH）
   - 图有、代码没有 → `STALE: 已删 <名>`（MEDIUM）
   - 全对齐 → `OK`

## 输出示例

```
[drift] 扫描 128 模块 / 图内 31 节点
FAIL  Architecture Drift
  DRIFT  PaymentService        代码新增，图缺失      src/pay/PaymentService.java
  STALE  OldCache              图有节点，代码已删
  -> 建议：更新 docs/diagram/architecture.md
```

## 退出码

| 码 | 含义 |
|----|------|
| 0 | OK，无漂移 |
| 1 | 有 HIGH 漂移 |
| 2 | 有 MEDIUM 漂移 |

## 接入 CI（可选）

```yaml
- run: node scripts/drift.mjs . docs/diagram
```

## 与人工维护的分工

- 脚本只管**结构性漂移**（模块增删改名）。
- 语义漂移（职责变了但名字没变）脚本测不出 → 靠 `decision.md` 的 ADR + 人审。

## 出口检查

- [ ] 每次大改代码后跑一次 drift？
- [ ] HIGH 漂移是否已更新图或写进 risks.md？
- [ ] 图节点名是否与代码类名可对应？
