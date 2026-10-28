# 验收报告目录

按用户指示，本轮**跳过独立子代理验收步骤**（G1–G3 子代理因 ClinePass 周限额 429 失败；G4/G5 未启动）。

交付质量由以下可复现测试覆盖：

- `docs/TEST_REPORT.md`：数据规模/读音抽查、核心 40 例、全量 4447 例评估（含 300 例中段关键词）、预编辑分词、fallback/DP 置信度、真实 Rime 候选、GUI 提交、配置开关、共存、原生逐键性能；
- `tests/lua/run_cases.js`：核心用例；
- `tests/lua/bulk_eval.js` + `tests/cases/eval_cases.json`：全量评估；
- `experiments/rime-harness/rime_harness.py`：librime C API 集成测试；
- `docs/install-real-3.log`：本机真实安装/无头部署记录（开发机日志，仅保留在源码仓库，不进入分发包）。

如后续需要独立验收，可按 `PLAN.md` 的 G1–G5 门禁重新派子代理。
