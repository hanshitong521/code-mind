# fixture: java-reflection

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
