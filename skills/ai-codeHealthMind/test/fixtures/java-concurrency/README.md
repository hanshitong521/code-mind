# fixture: java-concurrency

## 用途
并发正例 + 反例。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-SHARED-MUTABLE | `src/main/java/demo/conc/SessionCache.java` | HIGH |
| CHM-JAVA-NAT-SEMAPHORE-LEAK | `src/main/java/demo/conc/PermitGate.java` | HIGH |
| CHM-JAVA-NAT-LOCK-REMOTE-CALL | `src/main/java/demo/conc/LedgerService.java` | HIGH |
| CHM-JAVA-NAT-DOUBLE-CHECK-NO-VOLATILE | `src/main/java/demo/conc/LazyConfig.java` | HIGH |
| CHM-JAVA-NAT-NO-IDEMPOTENCY | `src/main/java/demo/conc/PayController.java` | HIGH |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `ConcurrentSessionCache` ConcurrentHashMap | 线程安全容器 | CHM-CON-002 |
| `SafePermitGate` release 在 finally | 异常路径也归还许可 | CHM-CON-003 |
| `PrototypeScratch` `@Scope("prototype")` | 每次注入新实例，无共享状态 | CHM-CON-002 |
