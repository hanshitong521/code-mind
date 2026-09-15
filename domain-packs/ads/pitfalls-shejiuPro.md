<!-- ref-index -->
# 深读索引 · 每轮≤1册;Grep锚点或Read≤120行
工作区有`.cursor/skills/ads-sql/`时优先用仓内分册(SSOT)。
pitfalls：SSOT=`E:/workA/shejiuPro/.cursor/skills/ads-sql/pitfalls-shejiuPro.md`；本目录副本与业务仓同步（`install.ps1 -Force`）。
|hit|文件|
DML写改|reference/01-write-dml.md（仓内）|
查询JOIN/CAST|reference/02-query-types.md（仓内）|
DDL|reference/03-ddl-patterns.md（仓内）|
PK/ID/报错码|业务仓 ads-sql + pitfalls 表；04/05 分册已删|
无仓副本|本目录`pitfalls-shejiuPro.md`

---

# shejiuPro ADS踩坑 · sql-ads-distill/ads-sql 写Mapper前Read;只改本文件+distill红线
维护:新坑+行;Junction无需update;Copy装跑update.ps1
|ID|日|点|症状|根因|修复|
|P77|08-26|t_red_packet_issue|想 uk(task_id,round_no)|ADS 无 UNIQUE INDEX|Java 先查(task_id,round_no)+CAS status；INSERT CAST TINYINT 勿 SIGNED|
P76|08-24|ADS P0 perf|详情/监测/比价/券/同行款/发号|相关子查询+胖SQL+date_format+MAX子查询+MAX(id)+1|detailsInfoCommon窗口JOIN;monitor SortKey+hydrate;比价Java点查MAX(payment_time);券end_time>=NOW();同行款Java传roundNumbers;TableIdAllocator三表;日/周selectWeeklyStats tsp_dedup|
P75|08-24|weekStats copyOverview|prod ~44s|复用listStats后再打2次日统计；日/ForReport仍tsp_dedup全表GROUP BY|日ListDate+ForReport复用weekStatsTspDedupJoin；空列表只ForReport+fill不双跑日统计|
P74|08-24|团长导入回填company|全站卡；审计UPDATE t_buyin_order JOIN vucd 46s×45/2h|importOrderDetails每次无WHERE全表写已对齐行（test join 208万 need_write≈2）|updateTGroupOrderCompanyId加 WHERE company_id IS NULL OR <> vucd.company_dept_id；终态同、跳过空写|
P73|08-22|weekStats listStats|W1 32s/753MB|CAST(tbo.product_id AS CHAR)+tsp_dedup全表GROUP BY|窗口IN收窄+CAST(tsp.product_id AS BIGINT)；profit_data按周键；scoped_vps；见daily ads-sql-fix-playbook|
P72|08-22|Forge chunk.scope|scope=pitfall MCP 0hit;plain R1元文档Top1|索引scope=other+自测report进raw|ingest purge+store用classifyFileScope(path);bench默认mcp模式;见daily contextforge-v163-efficiency-root-cause-report|
P71|08-21|Forge scope handoff|HTTP scope=workflow首查0hit;pitfall首查可0hit|MCP无scope重查兜底;pitfall fallback仍错Top1元文档|handoff句靠MCP fallback;pitfalls禁信Top1必Read SSOT;见daily contextforge-deep-test-20260821|
P70|08-21|listForMonitorDown|下架页无达人名|未JOIN sys_dept|补sd.dept_name+JOIN tp.influencer_douyin_id；nickName仍选品人|
P69|08-21|weekCommentCount|评论 count/对齐全表扫超时|obc 无业务索引+锁 JOIN CAST(outer_store_id)|scripts/ocean_ddl/t_ocean_brand_comment_company_brand_index.sql；BrandCommentLockAlign 改 sl.outer_store_id=CAST(brand_id AS CHAR)|
P68|08-21|monitor 昨日成交|销量有成交0(收货单)|成交只认订单付款|认付款+收货+结算 isMonitorDealOrderStatus|
P65|08-20|INSERT SELECT CAST SIGNED|exception_type TINYINT列40040 BIGINT|ADS CAST AS SIGNED推断BIGINT|INSERT用jdbcType=TINYINT或裸绑定;勿CAST SIGNED写TINYINT|
P64|08-20|expireStoreLockLogs/主表|倒计时结束草稿不删(84480)|UPDATE…ORDER BY LIMIT 在ADS不落地;主表expire曾写0h|过期/slide/草稿删改id IN(子查询LIMIT);upsertBrandLock拒非未来expire|
P63|08-20|CG/Forge query|短名handle灌仓;踩坑→scope=pitfall 0hit;低分再Read全文|名碰撞+query-gate与规则互斥|CG用FQCN;Forge勿硬塞踩坑;0hit停;likely_irrelevant不Read;见daily mcp-dual-engine-opt|
P62|08-20|Agent MCP路由|改码首条Read/Grep烧票|explore歧义+Router不首工具|写码首条context_orient;口径semantic_search→get_evidence;见shared/core.md#pipeline-contract|
P61|08-19|评论门禁|刷完才强制评/待填≥10才拦|旧聚合门禁与刷新脱钩|reclaim+1 owed；owed>0禁刷采锁；评论区>15禁采锁；删待填≥10|
P60|08-19|audit productMonitorLiveUp|飞书上架失败中控台仍60|回滚用contains异常≠liveUpIsSuccess|audit/update 60路径!liveUpIsSuccess回滚;建联60延后百应成功|
|P67|08-21|brandHandle 折叠|FoldPick 全池更慢|test 粘住批窗函数≈GROUP BY|折叠/count 单路窗函数+PoolList；禁 FoldPick 双 SQL|
|P66|08-21|BrandHandlePool includeBrandIds|p0与p2粘住批列表相同|includeBrandIds空when跳过h.status|仅brandExpandMode跳过status；p2/0/1/全部分when；见daily brandHandle-seasList-tab-filter|
P59|08-19|BrandHandlePool status|粘住批按优先status砍回落品牌|死写status=1且列表再等值滤|includeBrandIds/expand跳过status；抽批handleStatus优先+回落凑30|
P58|08-19|listForMonitor tagIds|多选只命中一个|重复query只绑String末值|Controller applyMonitorTagFilter 合并为逗号串+find_in_set OR|
P57|08-18|t_source_store_lock.release_label_ids|listPendingReleaseReason Column cannot be resolved|731c22bc Mapper 未配套 DDL|scripts/ocean_ddl/t_source_store_lock_release_label_ids_column.sql 先 test 后 prod|
P56|08-18|t_ocean_brand_comment.comment_score|评论星级Unknown column|未跑DDL|scripts/ocean_ddl/t_ocean_brand_comment_score_column.sql 先 test 后 prod|
P55|08-17|t_ocean_brand_comment.shop_id|评论写入Unknown column|未跑DDL|scripts/ocean_ddl/t_ocean_brand_comment_shop_columns.sql 先 test 后 prod|
P54|08-17|Mapper foreach IN|9001 IN items>4000|一次传入>4000个绑定项|Java AdsSqlUtils.forEachChunk MAX_IN 3500 分片再查|
P53|08-15|expireStoreLockLogs|主表已释放日志仍0|同轮log/src各LIMIT300集合不一致|先扫空expireStoreLockLogs再expireSourceStoreLocks;slide/草稿删亦300批|
P52|08-15|品牌锁冻结|到期仍释放/草稿还在|expire未挡20/35/40/60|slide+expire NOT EXISTS四态;listForTemp返brandLockExpireTime|
P51|08-15|公海待填评论门禁|1个待填即禁采集锁|count>0即拦|待填去重品牌≥10才拦采集/公海锁|
P50|08-15|无运营品连扫Redis|李四2次张三继承计数|key仅company+brand|key加lockUserId;有运营品job先清零|
P48|08-14|backfill_finc_company_report|101成交单数≈2倍|裸JOIN v_user_company_dept乘行|与ReportAIUnionAll同:DISTINCT influencer子查询|
P47|08-13|ReportAIUnionAll|公司维 INNER JOIN 误放 WHERE|他人统一vucd口径时JOIN落WHERE|vucd JOIN 挪回 FROM；latest_tp 恒 outer+influencer|
P46|08-13|公司日总latest_tp|companyId Long 时 if 含!='' 可能整段不进|OGNL 数值比空串|ReportAIUnionAll 恒按 outer+influencer 分组JOIN；companyId 只判 null|
P45|08-13|oceanMiku insert|并发撞主键|SQL MAX+1/ROW_NUMBER|TableIdAllocator 预取 id+NOT EXISTS|
P44|08-13|公司日总亏品|221亏品187≠达人加总205|latest_tp按outer_product_id MAX(id)落到无cookie达人INNER JOIN丢单|公司维latest_tp按outer_product_id+influencer分组且JOIN订单达人|
P43|08-12|listForStatisAdmin|UI佣金/利润≠库行|list用bo.sum_total_commission与profit_data实时覆盖落库字段|对账落库看finc_statis_data；屏显佣金/利润是订单实时算
P42|08-10|日统计过审|过审>提交|approved按流水SUM重复20→35|视图approved改COUNT DISTINCT outer_product_id当日|
P41|08-10|brand/add新增锁定|误扣公司未运营3点|新增必未运营existsInCompanyBrandPool仍0|lockBrandAfterAdd chargeBrandLock exemptNotInCompany仍扣锁定1|
P40|08-10|224运营品牌测试|UI百品牌≠运营口径|运营中=shelfStatus1或company224的t_product10-60有brand_id|改状态只动本公司行且勿动他司同品牌30/40/60
P39|08-08|confirmStoreLink幂等|远程建联成功锁仍0|countUserLinkedStore不看过期link=1|幂等改countUserValidLinkedStore(expire>now)|
P01|07-08|OceanRankList insert|RESERVED_KEYWORDS|INSERT VALUES|INSERT SELECT FROM DUAL|
P02|07-08|同上|同上|根因VALUES非TINYINT|P01|
P03|07-08|同上|mismatched TINYINT|CAST只BIGINT|TINYINT双层CAST|
P04|07-08|tab列|保留字|tab保留|`tab`|
P05|07-08|rank_list|id雪花19位|未写id列AUTO大数|MAX(id)+1 rank_id业务键|
P06|07-08|brandHandle|INTEGER vs BIGINT|INT列禁CAST BIGINT|CAST(CAST AS BIGINT AS INT)查information_schema|
P07|07-08|brand_handle|id雪花|未写id|MAX+ROW_NUMBER cross join max|
P08|06-30|多Mapper|MAX+1并发|FOR UPDATE无锁静默|删FOR UPDATE Redis锁|
P09|06-30|~99 XML|getId null|useGeneratedKeys不回写|Service selectMaxId setId #{id}|
P10|07-07|SysJob pause|分布键|updateJob动态SET|updateJobStatus仅status|
P11|07-08|upsertBrandLock|ON DUP算术|DUP不可靠|UPDATE then INSERT NOT EXISTS|
P12|07-08|VisibleFromJoins|子查询|关联子查询|LEFT JOIN派生表 ROW_NUMBER|
P13|06|checkTagReturnRate|30000栈|深VIEW|直表查|
P14|06-30|AsyncCommonOrder|INSERT函数|VALUES禁函数|Java预计算paymentDate|
P15|—|batchUserRole等4表|暂可VALUES|无CAST简单VALUES|新Mapper禁VALUES|
P16|07-25|lifetime_agg|DECIMAL vs VARCHAR|参数当VARCHAR|CAST AS DECIMAL(18,2)|
写INSERT三步:1 SELECT/grep PK vs业务键 2 grep同表INSERT跟MAX或#{id} 3禁省略id列
CAST|场景|写法
禁|INSERT VALUES任意|整条禁
SELECT|TINYINT|CAST(CAST x BIGINT AS TINYINT)
SELECT|INT|CAST(CAST x BIGINT AS INT)
SELECT|BIGINT|CAST x BIGINT
WHERE|数值|CAST BIGINT
P08|删FOR UPDATE MAX+1|Redis
P09|禁useGeneratedKeys|Service预取setId
P10|pause/resume|updateJobStatus仅status列
P11|UPSERT|UPDATE updated==0再INSERT NOT EXISTS
P31|08-07|dailyStats listStats|601与752战绩差~980|601读视图profit_amount不含退货|VProductSelectorDailyStatsMapper左连finc_statis_data IFNULL(with_refund,amount)
P32|08-07|weekStats/listStats|接口慢|plan表6次全表window+46次targetSum|CTE单扫plan+周过滤;主查询带weekly_target_not_less_than_sum
P33|08-07|dailyStats listStats ForCompany|ADS 20021 correlated subquery|JOIN ON SELECT MAX(id)关联vps|GROUP BY create_user_id,data_time_str派生表+JOIN finc_statis_data;时间窗下推f2
P34|08-08|Ocean grant/锁店/历史建联|N次单品牌SQL|循环count/select|IN批查+tenant batch reactivate;listLinkBaselineProductsByLockLogIds
P35|08-08|t_ocean_product直写|DATE_FORMAT VALUES/30d增解析错|ADS禁VALUES函数;product_card_30d_data JSON|应用侧时间字面量;JSON列省略或合法JSON
P36|08-08|selectBrandHandleProducts|未对比行靠后|ORDER BY仅handle_id|buyin_missing=0(未对比)置顶再handle_id
P37|08-08|selectDistinctOperatingSelectorIdsByBrandAndCompany|P1锁后回补|distinct selector未滤null;锁人不在集合仍手动可建联|selector_id IS NOT NULL;锁人∈集合才自动confirm;多人运营不拦手动锁
P38|08-13|t_ocean_product.sales_30d|列不存在|insert/list 已绑 sales30d|先 ALTER 加列再发版；类型 varchar，Java String（禁 CAST BIGINT）
P47|08-13|oceanMiku/product/insert sales30d|Cannot deserialize String from Array|插件传 [{x,y}…] 数组，字段 String|JsonToStringDeserializer：数组→JSON 文本落 varchar
P48|08-13|oceanMiku/product/insert|sales_30d is not nullable, can not set null|列 NOT NULL，插件未传 sales30d|prepareProductRow 空则默认 []
P49|08-13|fillMissingBrandPriorities|每5min假「已补全」空转|下架人del无vucd仍入队+跳过写仍打成功|候选/缺失扫描须inner join vucd；upsert失败禁假成功日志
P50|08-15|BrandLockExpirePreserveStatusIn|过期删10/30|过期不删仅20/35/40/60;运营口径含10/30|XML refid 单点；运营 count 勿混四态
P51|08-15|logicalDeleteNonBlockingProductsForPendingReleaseLocks|误删他人草稿|仅品牌+公司 join|加 tp.selector_id=sl.lock_user_id；selector null 不删
P52|08-15|slideFrozenBrandLockExpires|停跑后集中过期|冻结期 expire 留过去|锚定 now()+1min；expire 每批300×最多20轮
P53|08-15|brandHandle/products/list|companyId有参无列表|handle status0或visible_expire过期|status=1+24h create_time+display1+round_key对齐+visible_expire>now
P54|08-17|expireStoreLocks 日志批收尾|末批<300仍跳过主表|if(lastLogBatch>0)误判未扫完|仅 lastLogBatch>=EXPIRE_LOCK_BATCH_SIZE 才 return 跳主表
P55|08-19|brandHandle/products/list test|404或旧语义|网关路径非/oceanMiku|用/prod-api/ocean/oceanMiku/brandHandle/products/list；p2去buyin须发版后验tao-only
|P62|08-20|brandHandle 置顶|remain=0仍顶/同轮重复顶|pin须in池+消费token=source_offline_time；remain=0禁回置顶并batch push_disabled|selectHandlePriorityPinBrandIds∩merged；Redis pin-consumed；池尽 disableHandlePriorityPushByBrandIds|
P63|08-21|selectTProductListForAudit_COUNT|ADS 20021 correlated company_id brand_id selector_id|NOT EXISTS嵌套相关子查询|listForAuditExpiredBrandLockHideJoin 派生表+LEFT JOIN；四态 p_blk GROUP BY 反连接|
|P64|08-24|copyOverview 500|ReflectionException weekStartTime on VProductSelectorDailyStats|DailyStatsMapper include weekStatsTspDedupJoin 引 week 字段|用 dailyStatsTspDedupJoin 仅 dailyTime/startTimeStr/endTimeStr|
|P66|08-26|t_red_packet_task.influencer_id|JSON 500 xiba0972→Long|列/实体误用 bigint|改 varchar+TRedPacketTask String；INSERT 用 #{influencerId} 勿 CAST BIGINT|
新行模板:|Pxx|日期|文件/接口|报错|根因|修复|
