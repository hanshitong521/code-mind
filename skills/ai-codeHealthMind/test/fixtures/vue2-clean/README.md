# fixture: vue2-clean

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
