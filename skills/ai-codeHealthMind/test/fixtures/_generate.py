"""Materialise every CodeHealthMind test fixture.

Usage::

    /d/APJ/Anaconda/python.exe test/fixtures/_generate.py

Standard library only.  Re-running is idempotent: files are overwritten with the
same bytes.  The generator exists so the fixtures are reviewable as code and so
a reviewer can see exactly what each fixture contains without opening 60 files.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _gen_java import JAVA_FILES, stub_files  # noqa: E402
from _gen_web import WEB_FIXTURES  # noqa: E402

#: fixture name -> java source prefixes owned by that fixture
JAVA_PREFIXES: dict[str, tuple[str, ...]] = {
    "java-clean": ("src/main/java/demo/clean/", "src/main/resources/mapper/OrderMapper.xml"),
    "java-dead-code": ("src/main/java/demo/dead/", "src/main/resources/mapper/DeadMapper.xml"),
    "java-duplicate": ("src/main/java/demo/dup/",),
    "java-overengineering": ("src/main/java/demo/over/",),
    "java-errors": ("src/main/java/demo/err/",),
    "java-concurrency": ("src/main/java/demo/conc/",),
    "java-performance": ("src/main/java/demo/perf/",),
    "java-db": ("src/main/java/demo/db/",),
    "java-reflection": ("src/main/java/demo/refl/", "src/main/resources/META-INF/services/"),
    "mixed-project": ("src/main/java/demo/mixed/",),
}


#: Extra files that are not part of the source payload (config, service
#: registration, ...).  ``source_roots: ["."]`` is required for the web
#: fixtures: ``package.json`` lives at the repository root while the default
#: source roots are ``src``/``app``/``lib``, so without it the dependency rule
#: would never even see the file.
EXTRA_FILES: dict[str, dict[str, str]] = {
    name: {
        ".codehealth.yml": (
            "version: 1\n"
            "mode: repo\n"
            "source_roots:\n"
            "  - .\n"
            "review:\n"
            '  backend: "off"\n'
            "baseline:\n"
            "  enabled: false\n"
        )
    }
    for name in ("vue2-clean", "vue2-dead-code", "vue2-duplicate", "mixed-project")
}


def java_fixture_files() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {name: {} for name in JAVA_PREFIXES}
    for rel, content in JAVA_FILES.items():
        for name, prefixes in JAVA_PREFIXES.items():
            if any(rel.startswith(p) for p in prefixes):
                out[name][rel] = content
                break
        else:  # pragma: no cover - generator bug guard
            raise SystemExit(f"java file {rel!r} is not assigned to any fixture")
    return out


READMES: dict[str, str] = {
    "java-clean": """# fixture: java-clean

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
""",
    "java-dead-code": """# fixture: java-dead-code

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
""",
    "java-duplicate": """# fixture: java-duplicate

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
""",
    "java-overengineering": """# fixture: java-overengineering

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
""",
    "java-errors": """# fixture: java-errors

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
""",
    "java-concurrency": """# fixture: java-concurrency

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
""",
    "java-performance": """# fixture: java-performance

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
""",
    "java-db": """# fixture: java-db

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
""",
    "java-reflection": """# fixture: java-reflection

## 用途
只在 `Class.forName` / `META-INF/services` / Spring `@Bean` 里被引用的类，
**必须全部不被报成死代码**。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| _（无 DEAD_CODE finding）_ | — | — |

`demo.refl.spi.Plugin` 有 2 个实现（JsonPlugin / XmlPlugin），所以也不该触发
`CHM-JAVA-NAT-SINGLE-IMPL-INTERFACE`。

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `spi/Plugin` + `spi/JsonPlugin` + `spi/XmlPlugin` | `META-INF/services` SPI 注册 | CHM-DEAD-007 |
| `PluginBootstrap` `ServiceLoader.load` | SPI 动态发现 | CHM-DEAD-007 |
| `Exporter.render()` | 方法名出现在 `getDeclaredMethod("render")` | CHM-DEAD-005 |
| `ExporterFactory` `@Bean exporter()` | Spring 容器注册 | CHM-DEAD-002 |
""",
    "vue2-clean": """# fixture: vue2-clean

## 用途
健康的 Vue2 组件 + 合理 API wrapper（有错误归一化）。与 java-clean 一样是
**假阳性基线**：不允许出现 MEDIUM+ finding。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| _（无 MEDIUM+）_ | — | — |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `src/api/user.js` `fetchUser` | `.then(...)` 做了响应归一化，不是纯透传 | CHM-JS-ABS-001 |
| `src/api/user.js` `fetchUser` | 被 `UserView.vue` import 并使用 | CHM-JS-DEAD-002 |
| `src/App.vue` `components: { UserCard }` | `<user-card>` 在 template 里使用 | CHM-JS-DEAD-001 |
| `package.json` 全部 dependencies | 都在源码里有 import | CHM-JS-DEP-001 |
""",
    "vue2-dead-code": """# fixture: vue2-dead-code

## 用途
Vue2 死代码正例 + 反例（全局注册 / 动态 import 路由 / `:is` 动态组件）。

## expected findings
| rule_id | file:line | severity |
|---|---|---|
| CHM-JS-NAT-UNUSED-COMPONENT | `src/views/Dashboard.vue` (UnusedWidget) | MEDIUM |
| CHM-JS-NAT-UNUSED-EXPORT | `src/utils/format.js` (formatMoney) | LOW |
| CHM-JS-NAT-UNUSED-DEPENDENCY-DECL | `package.json` (moment) | MEDIUM |

## forbidden false positives
| 代码位置 | 为什么是合理写法 | 关联规范编号 |
|---|---|---|
| `GlobalBanner.vue` 无 components 块 | 在 `main.js` 里 `Vue.component('global-banner', ...)` 全局注册 | CHM-JS-DEAD-003 |
| `LazyReport.vue` | 被 router 的 `() => import(...)` 懒加载 | CHM-JS-DEAD-004 |
| `DynamicHost.vue` 的 AlphaPanel/BetaPanel | 通过 `<component :is="current">` 动态使用 | CHM-JS-DEAD-005 |
| `src/utils/format.js` `formatDate` | 被 `ReportView.vue` import | CHM-JS-DEAD-002 |
""",
    "vue2-duplicate": """# fixture: vue2-duplicate

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
""",
    "mixed-project": """# fixture: mixed-project

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
""",
}


def main() -> int:
    written = 0
    fixtures_root = HERE

    # Merge per-fixture maps: a fixture may contribute files from both the Java
    # and the web generator (mixed-project does).
    merged: dict[str, dict[str, str]] = {}
    for source in (java_fixture_files(), WEB_FIXTURES, EXTRA_FILES):
        for name, files in source.items():
            merged.setdefault(name, {}).update(files)

    for name, files in merged.items():
        root = fixtures_root / name
        for rel, content in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
            written += 1
        readme = READMES.get(name)
        if readme:
            (root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
            written += 1

    for rel, content in stub_files().items():
        target = fixtures_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written += 1

    print(f"wrote {written} files under {fixtures_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
