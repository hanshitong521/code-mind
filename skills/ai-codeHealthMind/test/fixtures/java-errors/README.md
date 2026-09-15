# fixture: java-errors

## 用途
错误处理正例（空 catch / catch 后 return null / HTTP 失败仍返回 success）+ 反例。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-EMPTY-CATCH | `src/main/java/demo/err/SilentFailures.java` (readConfig) | HIGH |
| CHM-JAVA-NAT-CATCH-RETURN-NULL | `src/main/java/demo/err/SilentFailures.java` (loadTenant) | HIGH |
| CHM-JAVA-NAT-SWALLOW-AND-SUCCESS | `src/main/java/demo/err/InventorySync.java` | HIGH |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `DegradeWithMetric.flagValue` | 有 metric + 明确安全默认值，是合理降级 | CHM-ERR-003 |
| `OptionalLoader.load` 返回 `Optional` | 用 Optional 表达缺失，不是 return null | CHM-ERR-004 |
| `AuditController.audit` Controller 兜底 catch | 全局边界，返回失败响应而非成功 | CHM-ERR-005 |
