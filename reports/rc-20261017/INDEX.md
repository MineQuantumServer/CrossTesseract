# 2026-10-17 候选证据索引

结论、范围和复现说明以 [RC报告](../../docs/RC_20261017_REPORT.md) 为准；本目录同时保留失败、未运行和通过记录，不能用文件存在推断通过。相对路径及SHA指向执行时实际输入，`scratch/`下的本机世界、冻结类路径和含凭据的原始配置不作为公共下载包。

|内容|入口|
|---|---|
|事前冻结目标|[目标](../../docs/RC_20261017_TARGETS.md)、[测量修订](../../docs/RC_20261017_MEASUREMENT_AMENDMENT.md)|
|环境及固定版本|[environment-final.json](environment-final.json)|
|最终79项构建/后端及7项必需原生测试|`intent-final-build-20261017T1130Z/`；原生为4基础、2正资产故障、1库存发现回归|
|真实ENOSPC、COMMIT应答丢失、完成容量、多发布组中断|`fault-evidence/`，范围见RC报告|
|最终八种原生组合156次执行|[矩阵](native-matrix-final-3647ded-r2-20261017T113417Z-7d0c0d98c45b.json)、`native-matrix-raw/`|
|矩阵残余合法资产及正常停服|[只读审计](matrix-poststop-sql-audit-3647ded-20261017T114439Z-f3d27d4e.json)|
|FE基线/候选的严格性能门|[JSON](fe-final-gates-20261017T122508Z-b25e736a.json)、[CSV](fe-final-gates-20261017T122508Z-b25e736a.csv)，实际exit2，SQL下降门未达|
|八类原因与方法计数的离线汇总|[JSON](fe-scheduling-summary-20261017T131453Z-7d900c04b496.json)、[CSV](fe-scheduling-summary-20261017T131453Z-7d900c04b496.csv)，缺测明确为UNMEASURED|
|三种已闭合材料模式逐阶段数据|[JSON](mix-summary-20261017T123940Z-24297b5c3b26.json)、[CSV](mix-summary-20261017T123940Z-24297b5c3b26.csv)|
|持续测试首轮smoke失败|[审计](soak-first-smoke-failure-audit-20261017T1243Z.json)、`soak-first-smoke-failure-artifacts-20261017T1243Z/`|
|新smoke控制器|[smoke2](rc-soak-v2-3647-smoke2-controller-20261017T124858Z-5b38b9ff.json)，60秒不代替60分钟|
|full2失败后独立资产审计|[SQL/WAL逐凭证核对](full2-failure-assets-20261017T140222Z-0688ebfa.json)、[停服后探针完整性](full2-probe-export-late-read-audit-20261017T1405Z.json)，不把3600秒输入完成当完整门通过|
|修复读取器后的新smoke|[smoke3](rc-soak-v2-3647-smoke3-controller-20261017T140614Z-54f4c9ce.json)，新世界、60秒，后续完整窗口独立判断|
|fresh完整60分钟与真实尾部排空|[full3 controller](rc-soak-v2-3647-full3-controller-20261017T140922Z-bf2f1b49.json)，实际3600.000101844秒、30组件对、363冷探测、三服正常退出；controller引用字节相同的原始report与事件流|
|仅公共报告的离线复算|[严格FE复算](offline-archive-only-recompute-20261017T140551Z-9532bf796f1e.json)，复算一致，性能判定仍为exit2|
|本地/CI逐字节一致及可访问构建|[身份核对](ci/3647ded-reproducible.json)、[GitHub artifact](https://github.com/MineQuantumServer/CrossTesseract/actions/runs/39028980854/artifacts/12099865685)|

前一候选功能源码为 `3647dede64cfc23e054dfa962fd127787cae14ec`，JAR SHA256为 `1ae895792a44ca791a8ae1b6516ab35014f4c7e769e4aaccc016aa9adb2d074f`。该GitHub artifact需登录、保留90天，是测试候选而非正式发行版。后续证据/文档提交不改变该功能JAR身份。

原始性能窗同时报告固定输入期和真实排空/静止确认后的完整成本。计数中的SQL helper语句不是全部JDBC网络语句；SQL、WAL和RX是同一凭证的不同记录，不能相加为多份资产。不同资源单位也不相加。配置备份只公开SHA或明确脱敏副本，不发布数据库和RCON口令。

当前后补核心为 `0113ef30f2269f9ea51e7c15e585792828fd2a51`，JAR SHA256 `70a02e49900dee34fc996bfcf95360689ea9e42c35996c581c52df2ee6fdb07c`。其独立三布局、材料、八组合与60分钟重测已闭合；旧1ae持续结果不外推到新候选。

|后补证据|入口|
|---|---|
|原Runtime连续消费正资产负对照|`discovery-negative-20261017T1534Z/`，208FE合法保留，不退款重放|
|修复版82项后端/单元与8项原生测试|`discovery-positive-0113ef3/`，288FE实际输入输出守恒、新128在1.487秒发现|
|旧候选四模式材料闭合汇总|[JSON](mix-summary-20261017T153326Z-2e8be30c9178.json)、[CSV](mix-summary-20261017T153326Z-2e8be30c9178.csv)|
|旧候选完整小时派生与停服SQL|`soak-final-3647-v2-full3-20261017.*`、`soak-history-post-stop-20261017T151243Z-97e2c72b.json`|
|旧候选回退观察器失败及普通stop清理|`normal-fallback-rc-full3-fb-152155-3a10-20261017T152155Z-57a0bfbf.json`、`normal-fallback-cleanup-20261017T152923Z-79f333d9.json`；没有执行新业务/切配置，不能列回退通过|
|真实原生来源WAL的无授权副本ENOSPC|`native-origin-enospc-copy-20261017T153821Z-2c933b4a/`，原32FE/32ID，生产journal真实ENOSPC，非Runtime/掉电或重复资产|

旧候选小时/四材料模式的公开归档独立复算见 [迁移性核验](archive-portability-20261017T154941Z-107a484f/verification.json)，不访问原scratch，原始/派生归属不变。

新0113ef3实际CI的同摘要构建： [身份](ci/0113ef3-reproducible.json)、[artifact](https://github.com/MineQuantumServer/CrossTesseract/actions/runs/39046319975/artifacts/12105383390)。与旧候选下载并列保留，不能混用。

新0113ef3八组合164次执行： [矩阵](native-matrix-final-0113ef3-20261017T154321Z-c6d821fc61ba.json)、[公开日志清单](native-matrix-raw/0113ef3/public-log-provenance.json)。

新矩阵的正常停服、配额与合法剩余资产： [限定只读SQL](matrix-poststop-sql-audit-0113ef3-20261017T155554Z-865ad4efe.json)，首轮SQL语法错误记录保留，未改账。

新0113ef3持续观察已独立通过完整3600秒、尾部排空/守恒及正常STOP：

- [full controller](rc-soak-v2-0113ef3-full-controller-20261017T162024Z-7a118565.json)，同名目录包含byte-identical原始report、events及completion。
- [汇总](soak-final-0113ef3-v2-20261017T155637Z-543147e1.json)、[逐接收端CSV](soak-final-0113ef3-v2-20261017T155637Z-543147e1.csv)。
- [停服后历史](soak-history-post-stop-20261017T172344Z-a22e1d36.json)、[实际进程/锁释放](discovery-release-proof-0113ef3-20261017T172457Z-58a4c086.json)。
- [完整串行父流程](discovery-followup-0113ef3-20261017T155637Z-543147e1.json)，全9阶段EXIT0。功能PASS不替代冻结性能门；cross较严延迟和SQL20%失败保留。

新0113最终性能比较和诊断：

- [严格FE门](fe-final-gates-20261017T173453Z-7e770cf1.json)：实际EXIT2，SQL20%与cross较严延迟失败。
- [六版本/模式材料阶段](mix-summary-20261017T173510Z-a1dd17ed680d.json)：不能从n1推总体p95。
- [三版本原因/方法](fe-scheduling-summary-20261017T173516Z-00e09eb271f3.json)：PARTIAL、缺测及重叠原因保留。
- [新旧候选与新小时精简摘要](discovery-offline-summary-20261017T173906Z-f3ca8a74.json)：173720首份派生错误保留，最新supersedes_derivation，不改原始数据。
- 首轮0113回退FAILED、闭合及poststop SQL见同目录normal-fallback相关报告；新正资产复验已独立通过，首轮失败保留。

当前0113严格FE门公开归档复算：[46份输入、零scratch/源码读取](archive-portability-0113-fe-20261017T174550Z-11757c58/verification.json)，实际EXIT2且全部门逐值一致。

当前0113同JAR正资产配置回退：[实际报告](normal-fallback-rc-0113-fb-2bf6a319-20261017T175750Z-0f0f6f38.json)、[实际CLI退出/锁释放](normal-fallback-release-0113ef3-20261017T180354Z-9b4c4143.json)。945FE接受=输出、原LOCAL75/pool61两次跨配置、OFF提取0、9个Popen EXIT0；工具20项离线校验与显式闭合入口单独归档。首轮失败不改判。
