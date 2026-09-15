# 多图块文档

```mermaid
flowchart LR
  A["第一张"]:::step --> B["保留"]:::step
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
```

```mermaid
flowchart LR
  C["第二张"] --> D["应被忽略"]
```
