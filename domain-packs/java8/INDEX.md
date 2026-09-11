# java8 pack · JDK8 写法与质量门（命中 Stream/Lambda/Optional/341 时读）

- 禁 JDK9+ API；`var`、模块系统、新集合工厂等见业务仓 JDK。
- Stream：优先简单循环；并行流须有证据；Optional 禁 `.get()` 无判空。
- 互操作：JDBC/日期用 `java.time` 注意 JDBC 映射；JSON 字段与 DTO 一致。
- 质量门落地：`quality-gates.md`（P3C / format / SpotBugs 等按仓配置）。

路由：由 `/ai-code` 的 domain-pack 触发；每轮 ≤1 文件，够则停。


---
# quality-gates

# quality-gates · 自动化质量门工具链 · LeanCode §23 落地(java8仓)
原则:工具负责拦AI遗忘的规则,非"看起来专业";仓内无基建禁装(ai-code paradigm);接入前按本仓校准阈值,禁照抄默认
接入序:低噪先行(GJF/P3C)→缺陷门(ErrorProne/SpotBugs)→需调参门(CPD/ArchUnit)→专项(rewrite);每次接入过lean-gate依赖门
## 工具表(用法经源码仓核实)
能力|工具|用法
Java规约|P3C|com.alibaba.p3c:p3c-pmd(PMD引擎);规则集ali-naming ali-exception ali-concurrent ali-flowcontrol ali-oop ali-orm ali-set ali-comment ali-constant ali-other共10个xml;挂maven-pmd-plugin引规则集或pmd CLI -R
统一格式|google-java-format|java -jar google-java-format-*-all-deps.jar --replace <files>;CI门:--dry-run --set-exit-if-changed;局部:--lines;运行JDK版本≥被格式化源码语言版本(master分支现要求JDK21,JDK8仓选用仍支持旧JDK的发行版);Maven集成推荐Spotless googleJavaFormat()
编译期缺陷|Error Prone|javac -Xplugin:ErrorProne;bugpattern清单errorprone.info;运行JDK随发行版收紧(master构建source=21);JDK8仓用仍支持的旧发行版,或以P3C+SpotBugs兜底
字节码缺陷|SpotBugs|com.github.spotbugs:spotbugs;mvn com.github.spotbugs:spotbugs-maven-plugin:check;effort/threshold与excludeFilterFile按仓校准
重复代码|PMD CPD|mvn pmd:cpd-check;minimumTokenCount默认100,按仓调参防误报;hit→ai-code lean-gate语义重复收敛,非只报告
架构边界|ArchUnit|com.tngtech.archunit;JavaClasses importedClasses=new ClassFileImporter().importPackages("com.myapp")→classes().should()…check();存量违规不阻塞:FreezingArchRule.freeze(rule)记存violation,freeze.store.default.path入版本库,只拦新增
批量安全重构|OpenRewrite|org.openrewrite.maven:rewrite-maven-plugin;先mvn rewrite:dry-run核diff再rewrite:run;recipe族cleanup/migrate;批量替换手扫
未用依赖|Maven内置|mvn dependency:analyze;Unused declared→候选删除(过死码门动态入口排查);Used undeclared→显式声明
SQL|EXPLAIN|慢SQL先EXPLAIN;EXPLAIN ANALYZE真执行仅安全读/测试库;对拍档位→ai-code verification-gate
行为正确性|对拍|unit/integration/API/SELECT双向对拍→rigid-validation
## 消费规则
hit慢/重复/越界→先判业务语义(lean-gate)再动工具;工具报告≠必须修,须人裁决语义
ArchUnit规则写进测试即契约;禁为绿改断言(rigid-validation测不可篡改)
接入后工具门进LOCAL SELF-CHECK档位(verification-gate);仓内无该基建→禁虚构已接入
sonar-java=聚合伞可选,不替上列单项门
