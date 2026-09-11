---
name: ai-debug
version: 1.1.0
description: >-
  /ai-debug only. Root-cause loop: OBSERVE→REPRODUCE→LOCALIZE→HYPOTHESIZE→DISPROVE→ROOTCAUSE→FIXCONTRACT.
  no NL load.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/ai-debug prio:rules>this load:本页 ref命中单读 禁ref批
axiom:evidence>guess 一次一假设 最小实验证伪 禁连续补丁
ssot:../../shared/core.md
loop:OBSERVE→REPRODUCE→LOCALIZE→HYPOTHESIZE→DISPROVE→ROOTCAUSE→FIXCONTRACT
G-pre:现象+证据+复现路径?否→先复现再谈修复
G0 OBSERVE:现象/报错/环境/时间线;1行判据
G1 REPRODUCE:最小复现;复现不了→标不可复现禁猜修
G2 LOCALIZE:git show HEAD --path对拍;二分;调用链;死参数/双路径检
G3 HYPOTHESIZE:单一最小假设;禁多假设并改
G4 DISPROVE:最小实验证伪;证伪→回G3;证实→ROOTCAUSE
G5 ROOTCAUSE:根因一句话+证据;未钉根因禁进修复
G6 FIXCONTRACT:修复边界+回归面;交/ai-code最小diff;禁失败扩diff
pivot:STOP标废弃删旧再写;禁if legacy叠;净增>30→accumulation+ponytail-review
ship:`根因|假设|证据|证伪项|修复边界|回归面|下一步:/ai-code`
ref:细则→../ai-code/references/refs.md#systematic-debugging |栈→../../shared/core.md
STOP:无复现就改|多假设并改|猜原因直接改|失败后扩diff|未钉根因宣称修复|连续补丁|手抄旧版|只看最终文件|一例升STOP
link:/ai-code(修复) /ai-design(根因=设计缺陷)
