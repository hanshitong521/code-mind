# lean · /ai-code 默认写码路径（随 SKILL 加载）

最好的代码是没写的。先读完触及流，再爬梯。少 LOC ≠ 好：少概念、少重复、少分支、可验证。禁为压行数写晦涩/魔法SQL/巨型方法。
语义守恒：公式、权限谓词、状态边、兜底行 ≠ 死码；删口径须 /ai-design + 对拍。

## 梯（停在第一档成立的）

1. 这需求要存在吗？设计交付已覆盖 → 只补缺口，否则回 /ai-design
2. 仓内已有？grep/codegraph 同职责 → 扩展，不另造
3. JDK / 语言标准库能做？用它
4. 已有依赖能做？用它；禁为十几行引新库
5. 能一行？一行
6. 才写最小新码

Bug：grep 该函数全部 caller，在 choke point 修一次，禁只补票据路径。

## HIST-CLEAN（触及区必做，动手前 + Green 后）

已打开或将改的每个文件 = 触及区。禁未打开模块的全仓大扫除。

扫：未调 private · 不可达分支 · 注释旧实现 · 临时 Debug · 失效 SQL fragment · 本次替换后引用归 0 的旧方法 · 同包 `XxxV2` / 复制 DTO / 同表第二份 SELECT · 被替 Controller 路由 · 恒 true 兼容 flag

删前动态入口：`@RequestMapping` `@Scheduled` `@EventListener` Bean 扫描 MyBatis XML 反射 SPI 配置类名 RPC。公共 API 无法证明无外部消费者 → `@Deprecated` + Manifest，禁直删。

证据：grep 引用=0 + 配置无类名 + build/test 绿。
`deleted:` 必填。真没有 → `deleted: none` + 一条 grep（文件:符号）。净增行而无 deleted → FAIL。

Replace don't layer：旧被新完全替代 → 同 PR 删旧。禁 if-legacy 叠。双轨仅当外部消费者/灰度/用户明示，且写删除条件+期限。

## 新建四问（任一答不出 → 禁创建）

1. 仓内同职责？证据路径
2. 为何不能改现有？
3. 新文件减概念还是增？
4. 将来好删吗？

不值得抽：`handleData` `processResult` `doSomething` 无业务含义的三行跳转。值得抽：独立业务概念、复用、隐藏复杂、稳定验证接缝。

默认可疑：`XxxV2` `NewXxxService` `CommonHelper2` `TempUtil` 复制 Mapper/SQL 一次需求一个 Service/DTO。

语义重复必收敛（金额/状态/权限/时间窗/佣金/口径/枚举映射）。偶然相似禁为 DRY 合并。

反模式 → 对：加字段却 V2 → 原类加字段；复制 SQL 改 WHERE → 复用+if；两 Service 同计算 → 一处；状态字面量多处 → 枚举。

## 复杂度 / Diff / 依赖

命中审查：≥3 层嵌套 · 一方法多阶段 · 一串 boolean 参 · 大段 else-if · Service 兼查询计算权限外调。优先提前 return / 消分支 / 复用领域对象，禁第一反应再造五个类。for 比 Stream 清晰就用 for。

小需求改 ≥10 文件 → 须证明是真实爆炸半径。新 Maven 依赖四问：JDK？已有库？已有工具？值得长期养？

SQL：列真需要 · 已有同查询 · WHERE 早滤 · JOIN 必要 · 禁无义 DISTINCT / SELECT * / 循环 SQL。性能宣称须 Before/After+计划+对拍；禁见慢就加索引。

## Zero-bloat（存在即继续删）

还能删什么 · 旧入口未删 · 双轨 · 一次性 Helper · 为未来假设写的码 · 同一规则写两遍。`parallel_implementation=yes` 禁完成。

注释写为什么（给谁、什么业务问题），不写代码在干嘛；比代码长则删。捷径标 `// yagni: 上限+何时升级`。
禁 YAGNI 掉：身份矩阵 · 状态回流边 · SQL 探针 · 三路证伪。

STOP:未过四问建文件|无业务含义抽方法|语义重复未收敛|IDE灰即删|动态入口未查就删|触及区未扫死码|净增无deleted|为简洁删口径|双轨无期限|顺手重构全模块|小需求大diff无理由|引库做十几行|zero-bloat未过即ship
