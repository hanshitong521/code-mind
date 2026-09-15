# Decision Impact Graph（P1-02 · Phase 2）

从 `decisions.json` 生成 `.requirementmind/decision-graph.json`，供修改决策时查影响面。

## 结构

见 `schemas/decision-impact-graph.schema.json`。

冻结时尽量填结构化影响：

```bash
node $SKILL/scripts/state.mjs freeze .requirementmind Q-007 B --impact "order,user" --impact-files "src/order/*.java" --impact-tests "OrderServiceTest"
```

（`--impact` 仍兼容自由文本列表；`--impact-files` / `--impact-tests` 写入 graph。）

## 重建

```bash
node $SKILL/scripts/state.mjs impact-graph .requirementmind [--write]
```

Supersede 后重跑，保留 `SUPERSEDED` 节点与 `superseded_by` 链。
