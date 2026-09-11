# ai-code references (merged)


---
# agent-discipline

# agent-discipline · 公理赢
1读先于没有:Grep/Read/codegraph后才说无
2主张≤Fresh证据
3搜探先于猜现状
4提示有文件≠在须确认
5批评后核实再改 code-review-gates六步
6提速不删生效口径须对拍
7反谄媚公理0
8顶嘴HOLD或CHANGE+新证据
9约束终局:先钉G0判据与可跑闸门;禁用逐行读码冒充验证(见verification-gate§人审边界)
10子代理:多面并行按下述纪律;宿主汇总L1/ship;禁子代理代完成
11合并/替换API或入口:删被替代HTTP路由与死码;先grep仓内引用;同步契约/文档;Change Manifest写contracts_changed;仅用户明说保留兼容或未迁移外部依赖才双轨(≠禁删口径)
对应:Explore verification-gate 语义守恒 glossary 公理0


---
# change-manifest

# change-manifest · =handoff code_to_test;禁散文完成
必填:变更面|plan引用|已跑验证|未跑验证|建议下一步
选填:改动文件|验证写库恢复|剩余风险|规则演进|接入门|identity_matrix|verification_escalation
lean块(负代码命中才填;全量→lean-gate.md): reused_symbols reused_sql reused_models|removed_files removed_methods removed_branches removed_dependencies|new_files new_public_api new_dependencies|complexity_reduced complexity_introduced+justification|sql_explain_before sql_explain_after result_parity|lean_verdict minimum_effective_change:PASS/FAIL;parallel_implementation: yes禁完成→先收敛再交
plan引用:`@path.plan.md`或无plan写`@Handoff`
已跑验证:cmd+exit或SELECT摘要;禁裸✓
未跑验证:无|维:原因;只补所列维
建议下一步:enum /ai-design|/ai-code|/ai-debug|无
identity_matrix:过滤权限tenant→yes;否则na+原因
verification_escalation:命中verification-policy→yes
ship三行外再贴yaml块;可 `python scripts/validate_handoff.py`

```yaml
变更面: backend/api
plan引用: "@docs/plan/foo.plan.md"
已跑验证: "mvn -pl m -am compile -DskipTests -q exit=0"
未跑验证: 无
建议下一步: 无
identity_matrix: na
verification_escalation: na
```


---
# code-comments

# code-comments
律:写为什么业务用途不写代码在干嘛
必写:查询接口1行业务问题+参返语义|公开API契约1-3行|复杂SQL JOIN≥3每JOIN一行why|捷径 yagni:上限触发
禁:复述i++|变更日志|20行设计|只复述方法名
模板一行:查X用途;uid=;空=无数据还是无权限
判定:注释能答给谁什么业务问题;比代码长删


---
# code-quality

# code-quality ai-code独有
删测试问:删复杂度集中还是搬走?集中留搬走删
深模块:接口小实现深;BAD多方法校验 GOOD validate返回首因
命名:新建前grep Service|Manager|Helper同义→reuse-patterns
自检:删是集中还是搬走|grep同义|无顺手无关改


---
# code-review-gates

# code-review pr-ready · 先过verification-gate
双轴:Standards=AGENTS rules lint|Spec=plan验收scope creep;分开报findings
OCR:where ocr||npm i -g @alibaba-group/open-code-review;无ocr→双轴手工 git diff base...HEAD 注OCR❌
1 preview [--from --to|-c] [-b ctx]→mode files refs
2 rule path...→规则分组 --rule|.opencodereview/rule.json|ocr rules check
3 diff: range git diff merge_base..to | commit git show | workspace git diff HEAD | untracked Read全文
4 每文件diff+rules+双轴
5 comment path content start_line end_line category severity; line0→读文件定位
6 severity: critical/high→Critical必修|medium→Important|low→Minor有价值才报
7 fix仅用户要review+fix; Critical直改 Important描述 Minor跳过
flags:--from --to -c --repo --rule --exclude -b -B
got:delegate无LLM|untracked Read|cwd=git根
收反馈:读懂验证评估再改禁表演附和
禁:未pr-ready验证就review|Critical未修merge|review替compile|有ocr却跳过步骤


---
# common-pitfalls

# common-pitfalls · 先读本表路由再开**一条**分册;禁整包Read;本仓专项→项目仓pitfalls优先
分册|Px|hit
pitfalls-a-orm|P01-06|PageHelper MyBatis XML Jackson
pitfalls-b-sql|P07-11|GROUP BY 方言 超长SQL
pitfalls-c-core|P12-28|映射 状态机 身份 回填
pitfalls-c-advanced|P29-38|契约 排序 对拍 金标
mapping-table-diagnostics|P16|映射表COUNT矩阵
路由|信号|路径
空列表|rows=0|SELECT存在→入口ServiceMapper→表名
过滤弱|total过大|COUNT矩阵+allowLegacy默认+mapping-table
报表不对|汇总≠明细|汇总SQL禁AVG(ratio)写读汇总三路径
慢|>1s|分段计时子查询N+1
权限状态|双用户对比|API+权限表+事件
侧效缺|主成功下游无|grep RPC吞异常
同状态矛盾|A能B不能|P20+pitfalls-c-core
筛参无效|createTime等|P22 grep query
列不存在|重构|P14 grep旧列
又待审|P23回流|false-alarm
缺数慢|P27三路COUNT
撞主键|P24
同步仍旧|P26 IGNORE
回填差几行|P28
排序契约|P29 grep字面量
同分乱|P30
优化后口径变|P31对拍
共享列|P32读者
传A出B|P33响应列
下游缺|P34
回填漏维|P35
差集|P36 A−B
外部指标|P37 metric-reconcile
假差舍入JOIN|P38


---
# delivery-report

# delivery-report · pr-ready/用户要PR→§1-7;默认SKILL 3行速查
must:/ai-code改码|SQL未验证禁标题完成
§1一句用户收益 §2文件表+diffstat新建/复用 §3勾选Explore证伪ponytail compile探针 §4证伪SELECT+写路径INSERT→SELECT→DELETE或UPDATE回查 __AI_TEST__前缀 node/mysql2 CLI §5风险待办 §6规则自检ads-sql ponytail SQL compile §7速查一行
未完成:写SQL探针❌+原因+待补DDL后探针
§8不替代§4 SQL证据


---
# lean-gate

# lean-gate · 负代码门 · LeanCode Extreme Gate 蒸馏
目标:业务语义完全等价下 最少代码/概念/分支/重复/文件/依赖 + 最小公开接口面/修改范围/维护成本
铁律:少代码≠好代码;少概念+少重复+少状态+少分支+清晰边界+可验证才是;禁为压LOC写晦涩/超长表达式/复杂Stream链/魔法SQL/巨型方法
终极一句话:先找到后复用;先删除后新增;先收敛后抽象;先证明后优化;最小Diff完成需求;改后仓库比改前简单
## 负代码优先序(每轮动手前固定)
DELETE>REUSE>SIMPLIFY>EXTEND>CREATE
死码能安全删→先删|逻辑能直接复用→不复制|稍扩展即可→不另造|同义多实现→收敛唯一|现结构确实无承担者→才新建类/方法/文件/依赖
默认可疑:XxxV2 NewXxxService CommonHelper2 TempUtil XxxManager 复制Mapper 复制SQL 一次需求一个Service/DTO/Helper/Util
## 新文件门(四问全过才建;逐问给证据)
1 仓库有无同职责实现? grep/codegraph/symbol search 证据
2 为何不能改现有? 单一职责或兼容性证据
3 新文件减概念还是增概念? 明确说明
4 未来删除容易吗? 依赖边界说明
任一答不出→禁创建;优先扩展现有稳定模型
## 新方法门(抽取非天然整洁)
值得抽:业务概念独立|会被复用|显著降认知复杂|形成稳定验证接缝|隐藏复杂实现缩小调用面
不值得:handleData processResult doSomething buildInfo 无业务含义三行抽取,反增跳转成本
目标=减认知跳转,非增方法数;否则保持局部代码
## 重复门(语义vs偶然)
语义重复必收敛(单一事实源):金额算法 状态判断 权限条件 时间窗口 佣金公式 统计口径 字段转换 枚举映射
偶然相似不抽象:代码像但业务概念不同→禁为DRY强行合并
触及其一仍有他处同义(跨模块公式/状态字面量/枚举)→未收敛部分必写Manifest risk_proposed,禁静默留下
禁复制粘贴应对变化;两处同公式比多百行普通代码危险得多
## 死码门(删前动态入口排查;禁仅凭IDE灰删)
触及区死码:未调private|不可达分支|废弃字段|旧API|被替Service|重复Mapper|废弃flag|无效配置|未用依赖|恒值兼容|旧DTO|注释历史|临时Debug
删前排查动态入口:@RequestMapping @Scheduled @EventListener Bean扫描 MyBatis XML 反射 SPI META-INF/services Jackson/JPA序列化 SpEL/OGNL 配置文件类名 脚本 RPC 外部HTTP 第三方调用者
删除证据=引用搜索+配置搜索+动态入口搜索+build/test;公共API无法证明无外部消费者→禁直删(仅标废弃)
## Touch-and-Clean(触及区清理)
每次修改顺带删:相邻确定未用变量|本次替换后引用归0的旧private|失效SQL fragment|已被本次正式替换的兼容分支
禁"既然来了顺便重构整个模块";清理触及区,不扩业务范围;代码随每次开发变少,不靠半年大重构
## Replace Don't Layer
旧被新完全替代→默认删旧;禁旧接口+新接口/旧算法+新算法/旧字段+V2字段长期双轨
仅允兼容层:外部消费者|灰度|版本协议|用户明示|无法一次迁移;须注:删除条件+期限+剩余消费者+迁移路径;永久兼容层=技术债非架构
## 复杂度预算(软门;命中触发审查,非机械LOC)
≥3层嵌套|一方法多业务阶段|大量boolean参|大量else-if|同变量多阶段变义|Service兼查询计算权限转换外调|类公开过多无关方法|靠大段注释才解释得通控制流
命中优先:消分支|提前return|拆业务阶段|消重复|收敛状态|减参数|复用现有领域对象;禁第一反应再造五个类
可读性判据:普通工程师第一遍能否读懂业务;for比Stream清晰就用for;高级语法≠高级代码
## SQL 极简门(非SQL最短)
目标:结果对+扫描少+IO少+CPU少+临时数据少+返回少
写前查:列集真需要|同查询已存在|WHERE早滤|JOIN全必要|N+1|重复子查询|无义DISTINCT|错用GROUP BY修重复行|索引列函数计算|排序真需要|分页排序稳定|能批量禁循环SQL|事务范围过大
默认禁SELECT *;复用稳定语义片段,禁塞成万能动态SQL
## 性能与索引门
性能宣称必有证据:Before+After+结果集+执行计划+扫描行+实测耗时+数据量;EXPLAIN;EXPLAIN ANALYZE真正执行,仅安全读/测试环境
改后双向对拍 旧结果−新结果 与 新结果−旧结果;禁"应该更快""加索引肯定快";禁提速换统计口径
禁见慢就加索引:先看现有索引/WHERE/JOIN/ORDER BY/GROUP BY/选择性/数据量/执行计划;新索引算写放大+磁盘+维护+与已有重复;调SQL用已有索引优先于加新索引
## 依赖门(每个新Maven依赖四问)
JDK能完成?|项目已有库能完成?|现有工具类能完成?|解决的问题值得长期维护吗?
只为十几行简单转换→禁引库;减依赖=减漏洞面/版本冲突/升级成本/构建时间/认知成本
## Diff 预算(完成后自检)
改N文件|新增N文件|新增类/方法|删除旧码量|新依赖|新公开API|有无平行实现
小需求改≥10文件→异常审查:须证明是业务真实爆炸半径,非实现设计过度;好改动=小Diff大效果
## Zero-Bloat 提交门(逐问,存在即继续精简)
还能删什么|重复逻辑|不必要新文件|旧入口未删|新旧双轨|一次性Helper|无用import|无用依赖|无义注释|为未来假设写的代码|能用已有结构却新造|能提前return的嵌套|同一业务规则写两遍
直到每段代码都有明确存在理由;parallel_implementation=yes 禁完成,先收敛再交(见change-manifest lean块)
## 计划意图自检(大refactor开写前30s)
旧测全列入?对拍工件谁生成?桥接谁验?测文件受保护?判据可机器检查?→任一否→/ai-design补Handoff
## 路由
新建前复用流→reuse-patterns|重构/双实现对拍→rigid-validation|性能档位→verification-gate|语义重复P15/P31→common-pitfalls|替换删死码→agent-discipline#11|工具落地→../../../domain-packs/java8/quality-gates.md(java8仓)
STOP:未过四问建文件|无业务含义抽方法|语义重复未收敛|偶然相似强抽象|IDE灰即删|动态入口未查就删|双轨无删除条件|见慢加索引|性能宣称无对拍|顺手重构全模块|小需求大diff无理由|引库做十几行小事|zero-bloat未过即ship


---
# mapping-table-diagnostics

# mapping-table P16 · COUNT改码前必跑
命中:条数多/过滤像没生效|NOT EXISTS mapping+allowLegacy*|映射表未回填仍大量数据
根因:mapping_total=0且allowLegacy默认true→NOT EXISTS(mapping)恒真→bypass全表
SQL形态:EXISTS(mapping tenant) OR (allowLegacy=TRUE AND NOT EXISTS mapping)
易误判:删锁条数不变→先COUNT矩阵非锁问题
COUNT|测什么
mapping_total|COUNT mapping
mapping_tenant|COUNT mapping tenant status=1
base_pool|业务基础条件无tenant
strict_pool|base+INNER JOIN mapping tenant
legacy_pool|base+NOT EXISTS mapping
读矩阵|mapping_total|strict|legacy默认|现象
0|0|true|≈base_pool bypass非数据bug
0|0|false|应≈0否则还有路径
>0|<base|false|正常过滤
>0|0|true|映射有但bypass仍开查默认
修复:收紧默认→code|回填→DBA/ai-code|多模式→设计分支
post-insert:同事务回查可**局部**临时legacy禁全局permissive
禁:未COUNT改JOIN|空表归因锁|收紧不回填|全局permissive修单点


---
# pitfalls-a-orm

# pitfalls-a P01-P06 · index→common-pitfalls.md
P01|dup LIMIT GET后POST|PageHelper ThreadLocal|每用PageHelper.clearPage|禁靠自动清
P02|ORDER ambiguous|JOIN排序裸字段|表别名tp.modify_time|禁裸字段给startPageWithMultiOrder
P03|SAXParseException XML|SQL里<未转义|&lt;或CDATA|禁标签体内<
P04|SELECT (v1,v2)非法|trim prefix/suffix带括号|prefix只关键字无括号|禁trim包值列表
P05|400日期解析|空格日期|@JsonFormat yyyy-MM-dd HH:mm:ss|禁默认Jackson推断
P06|前端ID末位0|Long>2^53-1|Jackson Long→String|禁Long JSON数字给前端


---
# pitfalls-b-sql

# pitfalls-b P07-P11 · index→common-pitfalls.md
P07|not in GROUP BY|only_full_group_by|SELECT非聚合进GROUP BY或MAX/ANY_VALUE|禁关only_full_group_by绕过
P08|Unknown column alias|外层引用子查询别名|外层重复表达式或CTE再包|禁假设跨层别名
P09|GROUP_CONCAT DISTINCT ORDER BY|方言不支持|两步去重或子查询预排|禁不查方言直接写
P10|statement too large栈溢出|嵌套JOIN超深|拆步SELECT删无用JOIN用CTE|禁继续叠子查询
P11|函数不存在|方言差异sysdate/IFNULL|查项目sql规则用ANSI|禁默认MySQL函数名


---
# pitfalls-c-advanced

# pitfalls-c-advanced P29-P38 · 对账→metric-reconcile · index→common-pitfalls
P29|排序/白名单猜UI名|wire名≠展示≠Java字段|grep调用方字面量三方对齐|禁凭Entity/UI猜契约;禁为typo开后端特例
P30|同分乱序次级反|只定主列ASC/DESC|plan钉次级方向+NULL/0+ASC/DESC双测|禁同分随便只测一个方向
P31|更快但数字/行集变|删仍生效公式/兜底/状态边|改前快照同窗对拍;加速改路径不删口径|禁compile+更快无对拍;语义守恒>删行数
P32|改total_*别处炸|共享列多读者|grep列名读者清单;宁新列或全量迁移|禁未扫读者改共享列语义
P33|传60出40|只核参数名未核WHERE列=响应状态列|契约:请求值→WHERE列→响应字段;抽应滤掉主键|禁只total>0
P34|主成功下游缺行|@Async火后不管|侧效丢数→同步或可证明投递+对账|禁正确性路径为墙钟再Async
P35|Admin对达人断崖|回填只打一维|身份维矩阵每维≥1对拍|禁单维绿宣称迁口径完成
P36|COUNT近仍差N|只比行数|A−B/B−A键差集样本|禁COUNT接近就PASS
P37|Excel口头与终值差|未钉金标只比终值|先金标;公式组件矩阵每层;单层PASS禁写已对齐|禁口头金标;禁底齐⇒战绩齐
P37矩阵填:状态集|费率源|×RR?|系数维|舍入序|展示列←存储列
P38|率齐仍差~10|round序不同|复现raw/逐单round/加总round|禁率齐就结案
P38|挂不上填0|INNER JOIN丢整单|COUNT buyin vs join后|禁教填0
P38|昨率算今|旧表缺新品|当日拉RR|禁昨日表套今日全量


---
# pitfalls-c-core

# pitfalls-c P12-P28 · index→common-pitfalls · P29+→pitfalls-c-advanced
P12|报表与明细不一致|读汇总存储未重刷|报表实时聚合源表|禁报表读汇总存储列算关键指标
P13|CAST SIGNED/UNSIGNED错|方言|CAST AS BIGINT|禁不查方言用SIGNED
P14|删SELECT字段后前端缺|未grep模板Service|grep Vue/二次赋值再删|禁凭印象删字段
P15|同表多DtoV2重复SQL|习惯性复制|grep同表实体/列复用|禁加字段就V2整段复制Mapper
P16|过滤像没生效条数≈全量|mapping空+allowLegacy默认true NOT EXISTS恒真|COUNT矩阵mapping/base/strict/legacy|禁未COUNT改JOIN|详→mapping-table-diagnostics
P17|换company/user组合错|只测一种入参|身份×入参矩阵每组合|禁单点compile绿
P18|修公司池漏总账号|choose只改一支|改前列when清单改后grep fragment|禁只改一条when
P19|插件companyId与token不一致|兜底取错源|矩阵含I3注释优先级|禁有companyId就行
P20|A能查B不能|状态字段只改一条SQL|grep字段全mapper触达清单同轮对齐抽sql片段|禁改1条SQL;禁同构list只改1个
P21|主表log不同步|unlock只更主表|Service主+log同批验收两表一致|禁只验主表
P22|传参筛选无效|VO有字段Mapper未query.xxx|grep query.{param}|禁VO有就能筛
P23|驳回后又待审|设计回流或环境错位|回流边+同环境SELECT+写路径日志+false-alarm|禁未证伪改CAST
P24|并发Duplicate|无锁MAX+1|Redis锁/序列|禁无锁MAX+1
P25|比率虚高虚低|JOIN多绑身份键缺组合|改前COUNT有/无JOIN键|禁silent COALESCE 0
P26|同步后字段仍旧|INSERT IGNORE同id|DELETE+INSERT或明确upsert列|禁IGNORE当幂等同步
P27|缺数/慢就改SQL|源无数据/键空/库错位|接口COUNT+事实表COUNT+源表COUNT|禁只看API绿
P28|回填exit0仍差几行|窗口内live writer|rows vs COUNT DISTINCT键+modify_time|禁脚本成功=一致


---
# reuse-patterns

# reuse · 新建前grep证明无现有
优先序:DELETE>REUSE>SIMPLIFY>EXTEND>CREATE;新建过四问:同职责已存在?为何不能改现有?增概念还是减?可删?→lean-gate.md
流:要新建X→grep同义?一致→扩展|破坏单一职责→新建注理由|无→新建注未找到
反模式|对
加字段XxxV2|原类加字段
复制SQL改WHERE|复用+if
两Service同计算|收敛一处
状态字符串多处|枚举常量
未grep新建|先grep
grep信号:class DtoV\d|FROM同表多SELECT|calc.*Amount|PAID字面量
流程:Explore→grep→扩展→最小实现
Bug:grep函数全部caller choke修一次
缜密区过滤权限金钱:身份矩阵+升档 verification-policy
yagni标记:// yagni:上限何时升级
禁YAGNI掉:身份矩阵|状态回流边|SQL探针|三路证伪


---
# rigid-validation

# rigid-validation · 大规模重构/双实现替换/桥接层
蒸馏:战棋 GDScript→C++ 自验证;Agent08 提示词「降模糊」仅保留与编码相关的子集
SSOT铁律:verification-gate;本文=何时必须刚性+两种对拍

## 刚性 vs 柔性（失败模式）
独立内核绿≠桥接绿|常见坑:第二阶段让 Agent 自拟「差不多」验收→假 PASS
规则:替换/FFI/Godot桥/Mapper换实现 与 第一期同档门禁;禁「compile+自写检查清单」替代可执行判据
柔性仅用于:探索原型、文档、非行为承诺的 UI 草稿

## 刚性套件（按可得性取子集,全有则全开）
| 闸门 | 判据 | 非证据 |
|------|------|--------|
| 单测直译 | 旧套件迁新语言/模块;触及路径 0 fail | 删断言/放宽期望 |
| 测不可篡改 | 改测须人审或独立 review;禁为绿而改期望 | 子 Agent 口头「测过了」 |
| 状态对拍 | 固定 seed 状态→旧新各走一步;决策/输出 bit 一致 | 抽样「看起来对」 |
| 金标/回放 | 录制的局/请求/JSON 回放 | 只跑 happy path |
| E2E 最小链 | 一条真实用户路径 cmd+exit 或 SELECT 摘要 | API 200 无体 |

桥接阶段额外:端到端一条链必须在目标运行时跑通(非仅单测);与 LOCAL SELF-CHECK 同 Fresh 证据

## 计划意图自检（大 refactor 开写前,30s）
问:旧测是否全列入?对拍工件谁生成?桥接谁验?测文件是否受保护?完成判据是否可机器检查?
任一否→/ai-design 补 Handoff 再 /ai-code

## Bug 投喂（多轮盲改时,补 systematic-debugging P0）
必带:复现步骤|预期|实际|原始日志(勿转述)|范围(文件/模块)
人先 bisect/断点定根因→再让 AI 写修复;禁「帮我修好」无五件套

## 与已有栈（勿重复装）
Vercel AGENTS 八条≈ponytail ladder+reuse;生产禁「无兼容直删」→ shejiu 须保留迁移/回滚
utilities/prompt(已退役) skill=误拒/CTF;任务边界用 G0「改|不改|判据」+ ai-design plan自检,不另建五段式 skill
工程师价值:设计闸门>手写实现;见 verification-gate STOP「信子agent|让用户测」

## 路由
双实现|语言迁移|桥接替换|Agent 自拟验收 → 读本页 + verification-gate
难 bug 五件套 → systematic-debugging


---
# systematic-debugging

# systematic-debugging · 无tight red环禁修生产
P0环:单测|SELECT|curl|CLI|playwright|replay|harness|fuzz|bisect|diff;收紧快尖稳;非确定→提repro率;建不了→列尝试要artifact禁改码
P0.1投喂:复现步骤|预期|实际|原始日志|范围;缺项禁盲改→人定根因再AI落地;rigid-validation
P0.5假阳性:回流F1|看错列F2|库无id F3|写日志F4-5|乐观F6-7→false-alarm;未过禁方言/CAST修
P1复现=用户症状最小砍至load-bearing|P2根因全栈grep callers choke修|P3 3-5可证伪假设|P4一变+log前缀DEBUG|P5最小测试先修再跑环|P6清DEBUG删harness
分工:SELECT证伪设计→/ai-code探针;证实改Mapper→ai-code P5;造数须用户授权
禁:未复现改|多处试|症状patch不查空因|无red就假设


---
# verification-gate

# verification-gate · 档位见SKILL tier;本文=宣称证据
范式:Agent产出=草稿;质量由可执行闸门裁决,非人眼逐行读码|人审兜底见§人审边界
## tier（验证档位 · 与 Handoff 一致）
|档|必跑|适用|
|m|lint/format|纯文案/注释无行为|
|l|build+触及单测+写SQL探针|默认业务改码|
|s|l+身份/状态/过滤矩阵或SELECT对拍|tenant/状态机/排序/共享列|
|p|s+一条API/E2E或回放金标|PR-ready/对外契约|
未达 Handoff 声明档位→禁 ship 完成|升档维→verification-policy.yaml
铁律:未Fresh跑验证禁完成|有测未跑触及单测禁完成|写SQL未探针禁SQL可执行|MCP只读须node/CLI探针|仅回填UPDATE≠INSERT探针|验证行禁裸✓须cmd+exit或SELECT摘要|无轨迹禁PASS|L1未绿禁PR-ready
五步法:IDENTIFY命令→RUN全量→READ输出+exit→VERIFY支持宣称→CLAIM附证据
宣称|证据|非证据
测过|0 fail exit0|上次跑过应该过裸✓
触及单测绿|过滤包/类 exit0|仅compile
compile|cmd exit0|linter裸✓
Bug修|原步骤+验证|看起来对
过滤权限|身份矩阵I0-n+SELECT|仅compile
SQL可执行|INSERT SELECT DELETE同形或UPDATE+回查|只compile只读XML用户测
状态机|grep字段全mapper对齐+全链路|只改一条SQL
更快|baseline同窗对拍|只更快删CTE无对拍
筛选|响应状态=请求值+对照主键|只total>0
回填口径|身份维+A−B差集|只COUNT单维Admin
外部对齐|金标+公式矩阵每层|只终值接近一层齐
侧效|主成功⇒下游行|仅API200
PR-ready|pr-ready全套|local仅compile
STOP:should/probably|未跑Great/Done|有测只compile|✓无cmd|commit前未跑|信子agent|让用户测SQL|MCP false就完成|回填当INSERT验|删口径无对拍|顶嘴改结论|L1未绿宣称完成
Handoff:已跑:cmd exit;未跑:原因禁宣称完成
## 人审边界（择优,非默认全流程读码）
不必逐行:scope内改动+档位l绿+ship三行附Fresh证据|micro唯一解读
必须人眼diff或升档:权限/金钱/PII|新对外契约无测|跨模块架构接缝|L1不可得(无测命令)|用户显式要review
禁:用「我读过了」替代未跑闸门|仓内无变异测/Gherkin却写进完成判据
