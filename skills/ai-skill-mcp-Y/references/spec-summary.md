# V1 摘要（日常够用; 全文见 spec-v1.md）

原则: 能力做大, 入口做小; 精准触发; 按需展开; 关键证据不丢。

优先级不可颠倒: 正确率 → P0证据 → 安全 → token → tool次数 → 延迟 → 维护 → 扩展。

治理不取代: RequirementMind(What) · Brain(Know) · TokenMind(See) · Skills/MCP(Do) · TestMind(Verify)。
治理=发现浪费/冲突/误触发, 给可验证改法。运行时 Router 只留一个权威实现。

Skill 根=路由器。MCP=大能力小暴露。AGENTS=导航不是清单。
Token 顺序: 不加载 → 不重复加载 → 不重复调用 → 缓存 → 增量读 → 筛选 → 摘要 → 深压缩。

评分仅作解释, 禁止用分数掩盖原始指标。上线: 正确/证据/安全 Gate + trigger 4类 + 回滚; 建议 ≥3 真实任务 A/B。

反模式: 万能 skill · description 写满工作流 · 根塞尽参考资料 · 一次暴露全部 tool · 只看压缩率 · 多层 Router · 每任务全量测试。
