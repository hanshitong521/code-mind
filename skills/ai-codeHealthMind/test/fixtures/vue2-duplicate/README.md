# fixture: vue2-duplicate

## 用途
重复 computed 正例 + 反例（<= 2 行的纯字段 computed）。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JS-NAT-DUP-COMPUTED | `src/views/ReportBoard.vue` (activeAdmins 复制 activeUsers) | MEDIUM |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `SimpleBoard.vue` `label()` / `count()` | 只有 1 行有效语句的纯字段访问 | CHM-JS-DUP-001 |
