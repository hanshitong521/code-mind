# pitfalls · 先读本表再开一条分册;禁整包当开工读。本仓专项→项目仓 pitfalls 优先

分册|Px|hit
a-orm|P01-06|PageHelper MyBatis XML Jackson
b-sql|P07-11|GROUP BY 方言 超长SQL
c-core|P12-28|映射 状态机 身份 回填
c-advanced|P29-43|契约 排序 对拍 金标 wire
mapping|#p16|映射表 COUNT 矩阵

信号|路径
空列表 rows=0|SELECT存在→入口 Service/Mapper→表名
过滤弱 total过大|#p16 + allowLegacy
报表不对|汇总SQL禁 AVG(ratio);写读汇总三路径
慢 >1s|分段计时 子查询 N+1
权限状态|双用户对比 API+权限表+事件
侧效缺|grep RPC 吞异常
同状态矛盾 A能B不能|P20
筛参无效|P22 grep query
列不存在|P14
又待审|P23 false-alarm
缺数慢|P27 三路 COUNT
改接口前端跟着改|contract.md + P39-P43

---
# p16

命中:条数多/过滤像没生效|NOT EXISTS mapping+allowLegacy*|映射未回填仍大量数据
根因:mapping_total=0 且 allowLegacy 默认 true → NOT EXISTS(mapping)恒真 → bypass 全表
SQL形态:EXISTS(mapping tenant) OR (allowLegacy=TRUE AND NOT EXISTS mapping)
易误判:删锁条数不变→先 COUNT 矩阵非锁问题
COUNT: mapping_total · mapping_tenant status=1 · base_pool(无tenant) · strict_pool(INNER JOIN mapping) · legacy_pool(NOT EXISTS mapping)
读矩阵: 0/0/true ≈base_pool bypass; 0/0/false 应≈0; >0/<base/false 正常过滤; >0/0/true 映射有但 bypass 仍开
修复:收紧默认→code|回填→DBA|多模式→设计分支
禁:未COUNT改JOIN|空表归因锁|收紧不回填|全局 permissive 修单点

---
# a-orm

P01|dup LIMIT GET后POST|PageHelper ThreadLocal|每用 PageHelper.clearPage|禁靠自动清
P02|ORDER ambiguous|JOIN排序裸字段|表别名 tp.modify_time|禁裸字段给 startPageWithMultiOrder
P03|SAXParseException XML|SQL里<未转义|&lt;或CDATA|禁标签体内<
P04|SELECT (v1,v2)非法|trim 带括号|prefix只关键字无括号|禁 trim 包值列表
P05|400日期解析|空格日期|@JsonFormat yyyy-MM-dd HH:mm:ss|禁默认 Jackson 推断
P06|前端ID末位0|Long>2^53-1|Jackson Long→String|禁 Long JSON 数字给前端

---
# b-sql

P07|not in GROUP BY|only_full_group_by|非聚合进 GROUP BY 或 MAX/ANY_VALUE|禁关 only_full_group_by
P08|Unknown column alias|外层引用子查询别名|外层重复表达式或 CTE|禁假设跨层别名
P09|GROUP_CONCAT DISTINCT ORDER BY|方言不支持|两步去重或子查询预排|禁不查方言直接写
P10|statement too large|嵌套 JOIN 超深|拆步 SELECT 删无用 JOIN|禁继续叠子查询
P11|函数不存在|方言 sysdate/IFNULL|查项目 SQL 规则用 ANSI|禁默认 MySQL 函数名

---
# c-core

P12|报表与明细不一致|读汇总存储未重刷|报表实时聚合源表|禁报表读汇总列算关键指标
P13|CAST SIGNED/UNSIGNED错|方言|CAST AS BIGINT|禁不查方言用 SIGNED
P14|删 SELECT 字段后前端缺|未grep模板|grep Vue/二次赋值再删|禁凭印象删字段
P15|同表多 DtoV2 重复 SQL|习惯性复制|grep 同表实体复用|禁加字段就 V2 整段复制 Mapper
P16|过滤像没生效≈全量|mapping空+allowLegacy|#p16 COUNT矩阵|禁未COUNT改JOIN
P17|换 company/user 组合错|只测一种入参|身份×入参矩阵|禁单点 compile 绿
P18|修公司池漏总账号|choose只改一支|改前列 when 清单|禁只改一条 when
P19|插件 companyId 与 token 不一致|兜底取错源|矩阵含 I3 优先级|禁有 companyId 就行
P20|A能查B不能|状态字段只改一条 SQL|grep 字段全 mapper 同轮对齐|禁改1条 SQL
P21|主表 log 不同步|unlock只更主表|主+log 两表一致|禁只验主表
P22|传参筛选无效|VO有字段 Mapper 未 query.xxx|grep query.{param}|禁 VO 有就能筛
P23|驳回后又待审|设计回流或环境错位|回流边+同环境 SELECT+false-alarm|禁未证伪改 CAST
P24|并发 Duplicate|无锁 MAX+1|Redis锁/序列|禁无锁 MAX+1
P25|比率虚高虚低|JOIN 多绑身份键缺|改前 COUNT 有/无 JOIN 键|禁 silent COALESCE 0
P26|同步后字段仍旧|INSERT IGNORE 同 id|DELETE+INSERT 或明确 upsert 列|禁 IGNORE 当幂等同步
P27|缺数/慢就改 SQL|源无数据/键空/库错位|接口 COUNT+事实表+源表 COUNT|禁只看 API 绿
P28|回填 exit0 仍差几行|窗口内 live writer|rows vs COUNT DISTINCT 键|禁脚本成功=一致

---
# c-advanced

P29|排序/白名单猜 UI 名|wire≠展示≠Java字段|grep 调用方字面量三方对齐|禁凭 Entity/UI 猜契约
P30|同分乱序|只定主列 ASC/DESC|plan 钉次级+NULL+双测|禁同分只测一个方向
P31|更快但数字/行集变|删仍生效公式/兜底|改前快照同窗对拍|禁 compile+更快无对拍
P32|改 total_* 别处炸|共享列多读者|grep 列名读者;宁新列|禁未扫读者改共享列语义
P33|传60出40|只核参数名未核 WHERE=响应列|请求值→WHERE→响应字段|禁只 total>0
P34|主成功下游缺行|@Async 火后不管|侧效丢数→同步或可证明投递|禁正确性路径为墙钟再 Async
P35|Admin 对达人断崖|回填只打一维|身份维每维≥1对拍|禁单维绿宣称迁口径
P36|COUNT 近仍差 N|只比行数|A−B/B−A 键差集|禁 COUNT 接近就 PASS
P37|Excel 口头与终值差|未钉金标|先金标;公式矩阵每层|禁口头金标
P38|率齐仍差~10 / JOIN 丢单 / 昨率算今|round序·INNER JOIN·旧表|复现 raw/逐单round; COUNT buyin vs join后;当日 RR|禁率齐结案;禁教填0;禁昨日表套今日
P39|改接口顺手改名|wire=前端字面量|grep 前端+VO+Controller|禁凭设计感重命名
P40|状态字段接口间不一致|新接口自造 state vs status|复用同模块既有名|禁另起状态字段名
P41|包装/分页与兄弟不一致|新接口另立包装|跟兄弟接口|禁另立包装
P42|GET 同义参异名|beginTime/createTime|grep 同模块 @RequestParam|禁同义参两名
P43|按模板定本仓 wire|外部习惯当规范|先探测本仓实测|详→contract.md
