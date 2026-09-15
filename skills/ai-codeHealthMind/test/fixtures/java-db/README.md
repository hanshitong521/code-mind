# fixture: java-db

## 用途
数据库正例（N+1 / UPDATE 无 WHERE / DELETE 无 WHERE / 事务内远程调用）+ 反例。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-NPLUS1 | `src/main/java/demo/db/OrderQueryService.java` | HIGH |
| CHM-JAVA-NAT-UPDATE-NO-WHERE | `src/main/java/demo/db/BulkMaintenance.java` | CRITICAL |
| CHM-JAVA-NAT-DELETE-NO-WHERE | `src/main/java/demo/db/BulkMaintenance.java` | CRITICAL |
| CHM-JAVA-NAT-TX-REMOTE-CALL | `src/main/java/demo/db/LedgerTxService.java` | HIGH |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `SafeQueries.prefetch` `selectList(chunk)` 分批预取 | 批量查询，不是逐条 | CHM-DB-002 |
| `SafeQueries.rename` `UPDATE ... WHERE id = #{id}` | 带 WHERE | CHM-DB-003 |
| `SafeQueries.firstPage` `SELECT * ... LIMIT 100` | 有 LIMIT 上界 | CHM-DB-004 |
