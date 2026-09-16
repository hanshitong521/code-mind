# 目录结构与模块职责

> 根文档 `SKILL.md` 的 `ref:` 路由表命中「目录结构 / 模块职责」时读本页。

```
codehealth.py          # 入口
src/chm/               # 引擎（纯标准库，ADR-001）
  schema.py            # Finding 标准模型（规范 §8）
  contracts.py         # ScanContext / ProviderResult / EvidenceProvider
  core/                # orchestrator·riskrouter·score·gate·baseline·dedup·validator
  context/             # git·symbols·packer·secretfilter
  adapters/            # 真实 CLI 适配器
  analyzers/           # 内建确定性分析器（Java / Vue）
  reviewers/           # 5 个 persona + 隔离 runtime
  reports/             # console·json·markdown·sarif
rules/                 # PMD 规则集（已验证）+ Semgrep 规则
docs/                  # 架构·schema·风险模型·规则编写·ADR
test/                  # fixtures·golden·adversarial·benchmark
```
