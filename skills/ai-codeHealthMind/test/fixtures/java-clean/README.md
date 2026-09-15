# fixture: java-clean

## 用途
完全健康的 Java 变更集，用作**假阳性基线**。跑完 `Orchestrator(mode=repo)` 后
**不允许出现任何 MEDIUM+ finding**（HIGH+ 更不允许）。这里覆盖的写法都是规范
明确要求「不得误报」的合理写法。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| _（无 MEDIUM+）_ | — | — |

LOW 级别的噪音也应为 0；若出现 LOW，golden 测试会打印但不判失败。

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `io/ReportReader.java` try-with-resources | 资源在 try(...) 头里声明，JVM 保证关闭 | CHM-RES-002 |
| `cache/SessionRegistry.java` ConcurrentHashMap | 线程安全容器，单例里可变也安全 | CHM-CON-002 |
| `order/OrderService.java` `selectBatchIds` 批量预取 | 一次批量查询，不是 N+1 | CHM-DB-002 |
| `order/OrderService.java` 注入 `Clock` | 时间可注入，可测试 | CHM-TEST-002 |
| `pricing/PricingStrategy.java` + 3 个实现 | 真实多实现，抽象有收益 | CHM-ABS-001 |
| `sdk/PaymentSdkAdapter.java` 单实现适配器 | 隔离第三方 SDK，是合法边界 | CHM-ABS-003 |
| `job/NightlyJob.java` catch(IOException) + metric | 有指标、有日志、有降级语义 | CHM-ERR-003 |
| `job/NightlyJob.java` `@Scheduled` | 框架调度入口，不是死代码 | CHM-DEAD-003 |
| `SpringComponent` 无显式 new | Spring 容器注册 | CHM-DEAD-002 |
| `src/main/resources/mapper/OrderMapper.xml` | MyBatis XML 调用 | CHM-DEAD-004 |
| `plugin/PluginLoader.java` `Class.forName` | 反射入口 | CHM-DEAD-005 |
| `ExporterPlugin.export()` | 方法名出现在 `getDeclaredMethod("export")` 字符串里 | CHM-DEAD-005 |
