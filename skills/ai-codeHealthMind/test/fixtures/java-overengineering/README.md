# fixture: java-overengineering

## 用途
过度抽象正例 + 反例（真实框架边界 / 错误语义归一化 / 真实多实现）。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE | `src/main/java/demo/over/OrderGateway.java` | MEDIUM |
| CHM-JAVA-NAT-SINGLE-CALL-WRAPPER | `src/main/java/demo/over/ReportFacade.java` | MEDIUM |
| CHM-JAVA-NAT-SPECULATIVE-FACTORY | `src/main/java/demo/over/PaymentAbstractions.java` | MEDIUM |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `InventoryClient` `@FeignClient` + 单实现 | RPC 边界，接口是契约 | CHM-ABS-003 |
| `NotificationSender` 两个方法都做了异常语义归一化 | 不是纯透传 wrapper | CHM-ABS-003 |
| `ChannelRouter` + SmsRouter/MailRouter/PushRouter | 真实 3 个实现 | CHM-ABS-001 |
