# fixture: mixed-project

## 用途
Java + Vue2 + package.json 混合仓，用于验证多语言**同时**扫描：一次
`Orchestrator(mode=repo)` 里 `native-java` 与 `native-vue` 都必须产出 finding。

`.codehealth.yml` 把 `source_roots` 设为 `["."]`，因为 `package.json` 在仓库根目录，
而默认 source roots 是 `src`/`app`/`lib`。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE | `src/main/java/demo/mixed/report/ReportGateway.java` | MEDIUM |
| CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE | `src/main/java/demo/mixed/api/OrderFacade.java` | LOW |
| CHM-JS-NAT-UNUSED-DEPENDENCY-DECL | `package.json` (moment) | MEDIUM |

`OrderFacade` 在 `demo.mixed.api` 包下，按规则降级为 LOW 并要求人工确认。

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `HealthEndpoint` `@GetMapping` | 只读端点，无写操作 | CHM-CON-004 |
| `src/App.vue` `components: { OrderBoard }` | `<order-board>` 在 template 里使用 | CHM-JS-DEAD-001 |
| `src/api/order.js` `fetchOrders` | `.then(...)` 做了响应归一化，不是纯透传 | CHM-JS-ABS-001 |
| `src/views/OrderBoard.vue` OrderRow/StaleBadge | 都在 template 里使用 | CHM-JS-DEAD-001 |
