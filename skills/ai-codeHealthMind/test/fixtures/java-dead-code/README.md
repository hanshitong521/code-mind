# fixture: java-dead-code

## 用途
死代码正例 + 反例。反例必须**完全不被报成死代码**，否则就是「删除机器」。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-UNUSED-PRIVATE-METHOD | `src/main/java/demo/dead/DeadCodeShowcase.java` (computeStaleTotal) | MEDIUM |
| CHM-JAVA-NAT-UNUSED-FIELD | `src/main/java/demo/dead/DeadCodeShowcase.java` (scratchBuffer) | LOW |
| CHM-JAVA-NAT-COMMENTED-CODE | `src/main/java/demo/dead/DeadCodeShowcase.java` | LOW |
| CHM-JAVA-NAT-TODO-MARKER | `src/main/java/demo/dead/DeadCodeShowcase.java` | LOW |
| CHM-JAVA-NAT-DEBUG-RESIDUE | `src/main/java/demo/dead/DeadCodeShowcase.java` (System.out.println) | LOW |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `ScheduledTasks.refreshIndex` `@Scheduled` | 框架调度入口 | CHM-DEAD-003 |
| `ScheduledTasks.onOrderCreated` `@KafkaListener` | MQ 入口 | CHM-DEAD-006 |
| `SpringComponent` `@Component` 无显式 new | Spring 容器注册 | CHM-DEAD-002 |
| `MapperSupport.selectByStatus` | 方法名出现在 `DeadMapper.xml` 的 `<select id="selectByStatus">` | CHM-DEAD-004 |
| `ReflectiveTask.invokeTask` | 方法名出现在 `getDeclaredMethod("invokeTask")` | CHM-DEAD-005 |
| `TaskBootstrap` 的 `Class.forName` | 反射入口 | CHM-DEAD-005 |
