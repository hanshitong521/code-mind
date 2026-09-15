# fixture: vue2-dead-code

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
