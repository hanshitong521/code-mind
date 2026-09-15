# fixture: java-performance

## 用途
性能正例（O(n²) 成员测试、重复序列化）+ 反例。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JAVA-NAT-ON2 | `src/main/java/demo/perf/Intersection.java` | MEDIUM |
| CHM-JAVA-NAT-REPEAT-SERIALIZE | `src/main/java/demo/perf/PayloadBroadcaster.java` | MEDIUM |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `HashLookup` `index.containsKey` | 哈希查找 O(1) | CHM-PERF-002 |
| `SmallLiteralScan` `Arrays.asList(3 个元素)` | 编译期常量且 <= 10 个元素 | CHM-PERF-003 |
| `SequenceIssuer` 只调用一次时间 API | 未超过 2 次，且无 Clock 需求 | CHM-TEST-002 |
