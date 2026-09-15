# fixture: java-duplicate

## 用途
重复代码正例（30 行完全复制 → CPD + 内建重复）+ 两类「相似但不得建议抽象」的反例。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-DUPLICATE-BLOCK | `src/main/java/demo/dup/InvoicePricer.java` | MEDIUM |
| CHM-JAVA-NAT-DUPLICATE-BLOCK | `src/main/java/demo/dup/SubscriptionPricer.java` | MEDIUM |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `RefundCalculator` vs `CouponCalculator` | 业务语义不同（退款 vs 优惠券），控制流结构也不同 | CHM-DUP-004 |
| `NullCheckA` / `NullCheckB` 的 `value == null` | 只重复 2 次且是普通 null 检查 | CHM-DUP-005 |
