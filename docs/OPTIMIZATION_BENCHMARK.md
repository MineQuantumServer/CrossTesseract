# 优化基准方法与复现

本文件定义 `scripts/optimization-benchmark.py` 的观察口径与复现条件。实际通过情况、性能值、失败及回归以对应 `reports/optimization-*.json` 为准；本文不填入估计性能。脚本可在未经优化的 `87bf217` 上运行，不依赖新的 Java 测试命令、迁移或生产配置。

## 环境与隔离

目标环境为 Minecraft 1.21.1、NeoForge 21.1.252、Java 21，三个独立 JVM，共用现有本机开发 MySQL 8.4.7 与 Redis 7.4.6。只接受以下目标：

| 服务 | 开发 RCON | 配置文件 | 群组 |
| --- | --- | --- | --- |
| A | 127.0.0.1:25575 | `run-A/cross-tesseract.properties` | `dev_three_v1` |
| B | 127.0.0.1:25576 | `run-B/cross-tesseract.properties` | `dev_three_v1` |
| C | 127.0.0.1:25577 | `run-C/cross-tesseract.properties` | `dev_three_v1` |

脚本强制校验开发后端 URL、账户、Redis URI、RCON 端口、实际进程 PID、`cross_tesseract.testHarness=true` 和配置路径。Java VM 参数文件只读取仓库 `build/moddev` 或 `scratch/dev-launch` 内对应服务的 `server*RunVmArgs.txt`；限制文件大小并拒绝嵌套参数文件。报告保存启动参数摘要、参数文件摘要和核验的非秘密系统参数，避免输出凭据。

允许既有 `dev-A/B/C` 身份，也允许 `opt-*-A/B/C` 的新开发身份。世界目录必须为 `world` 或安全的 `world-opt-*` 名称。校验实际世界 UUID 对应数据库中的有效会话，记录 SQL session ID 与 fencing epoch。基线使用 `opt-baseline-A/B/C` 和 `world-opt-baseline-A/B/C`，开始前 `registered_loaded_endpoints=active_endpoints=0`。脚本拒绝已有活动设备的世界，记录已有加载设备和其他有效 SQL 会话。

脚本不启停 Minecraft、Docker 容器或后端，不更改配置，不调用故障注入、quota 或 mod chunk-loading 命令。测试时创建独有 owner UUID、频道、远离已有测试区的真实方块，通过 vanilla forceload 保持自己的区块加载。每频道最多八个端点，低于旧默认上限 256。

## 运行

先进行无后端访问的自检：

```bash
python3 scripts/optimization-benchmark.py --self-test
python3 scripts/optimization-benchmark.py --help
```

关键路径的基线命令：

```bash
python3 scripts/optimization-benchmark.py \
  --label baseline-87bf217 \
  --scenarios same,cross,mixed \
  --warmup 30 --seconds 120 --repeats 3 --probes 40
```

每轮、每条路径有 40 次低流量探测、30 秒预热和 120 秒持续负载，共三个重复。低流量探测在每次输入前保持 2.2 秒安静期，还需等待真实输出；完整运行可能需要数十分钟。进度每十次探测输出一次，完整样本完成时输出业务量、每端输出和 DB 事务数。

背压和多频道热点单独执行，以便主路径与扩展场景分别保存、比较：

```bash
python3 scripts/optimization-benchmark.py \
  --label baseline-87bf217-pressure \
  --scenarios backpressure,hotspot \
  --warmup 30 --seconds 120 --repeats 3 --probes 0
```

优化版本必须使用相同参数、相同机器与 JVM 堆、相同后端/网络条件、干净开发世界和相同端点拓扑。将下方变量替换成已保存的真实基线文件，再运行：

```bash
CT_OPT_BASELINE_REPORT='reports/optimization-baseline-87bf217-YYYYMMDDTHHMMSSZ-runid.json'
python3 scripts/optimization-benchmark.py \
  --label optimized \
  --scenarios same,cross,mixed \
  --warmup 30 --seconds 120 --repeats 3 --probes 40 \
  --baseline "$CT_OPT_BASELINE_REPORT"
```

输出文件包含 label、UTC 时间和唯一后缀，旧报告不会覆盖。脚本预检失败、功能失败、异常中止或回归都会保存 JSON 并返回非零退出码。基线报告的 `conditions` 必须完全一致才能自动比较。

## 拓扑与业务事件

| 场景 | 输入 | 实际提取端 | 目的 |
| --- | --- | --- | --- |
| `same` | A1 | A2 | 同一 JVM 的真实能力接口路径 |
| `cross` | A1 | B1 | 跨 JVM 路径 |
| `mixed` | A1 | A2 与 B1 | 同服/跨服接收者共享频道，不复制广播 |
| `backpressure` | A1 | A2 与 B1 | 不提取时积压，再恢复实际提取 |
| `hotspot` | 四个 A 源输入同一热点频道，另有三个独立频道的 A 源 | 热点 A/B/B/C，冷频道分别 A/B/C | 热点竞争与频道间服务情况 |

FE 输入事件为 `ct_test push-fe` 返回的实际 `receiveEnergy(..., false)` 接受量，输出事件为 `ct_test pull-fe` 返回的实际 `extractEnergy(..., false)` 提取量。这是能力接口接受到能力接口实际提取的 E2E；本脚本不证明相邻真实机器或容器接收，不把 RCON 成功、数据库提交、WAL 写入或客户端缓冲到达当作世界保存完成。物品、流体、真实容器及异常恢复应由相应独立测试补齐。

持续负载默认每 0.5 秒一轮，每个源尝试输入 32,000 FE，每个接收端尝试提取最多 `Integer.MAX_VALUE` FE。端点本身的速率预算决定真实接受/提取量。每阶段固定 `ceil(seconds/feed_period)` 轮，120 秒即 240 轮；延迟的轮次仍执行，实际耗时和观察器滞后另行记录。单源在全额接受时为 7,680,000 FE 的固定尝试输入。热点四源的输入业务量为冷频道单源的四倍。

同一轮内按固定规则旋转频道和接收端顺序，避免每次都是同一个接收端先发 RCON 提取。每个端点记录实际输出、成功提取次数、首次与末次输出时间、最长未服务间隔；任一持续负载接收端实际输出为零即功能失败。低流量的混合接收分布保存在每笔探测中，只有实际被服务的端点才有该笔 E2E 数据。

RCON 的逐次主线程调度可能限制热点场景的驱动速率。报告中的 `observer_saturated`、`late_rounds`、实际窗口及 RCON 分位数必须一并阅读；饱和时不能把观测吞吐称为系统容量上限。固定事件数有助于比较同一业务负载的后端成本，此脚本不是服务器峰值容量测试。

## E2E 时间与 RCON 误差

所有时间来自同一 Python 进程的 `time.monotonic()`，记录为相对本次运行开始的秒数。绝不相减不同 JVM 的 `System.nanoTime()`。

每笔低流量输入为 1,024 FE；上一笔已实际全部提取后才开始下一笔。设源插入的 RCON 请求、应答时间为 `s0,s1`，实际提取的请求、应答时间为 `t0,t1`。真实插入和提取各自在自己的请求应答区间内，因此 E2E 使用以下区间：

```text
下界 = max(0, t0 - s1)
上界 = t1 - s0
```

报告同时保存完整原始事件、源/目标 RCON 往返时间、首次输出及全部输出的上下界 p50/p95/p99。目标轮询间隔默认 0.1 秒，也会延后实际提取事件。RCON TCP 建连、鉴权、服务线程排队、命令执行与回包均进入区间宽度；脚本不通过减去平均 RTT 制造精确单点时延。前后比较须保持 RCON 实现、调用顺序、轮询间隔和空闲期完全一致。

连续流量的 FE 输入可合并，没有逐笔业务标识。脚本仅对隔离低流量探测报告逐笔 E2E，连续阶段报告实际输出吞吐和服务间隔，避免捏造批次归属。低流量 p95 的统计单位是探测；自动比较使用三轮 p95 的中位数。

## SQL、事务与 WAL 口径

`ct_test status` 已有的 `db_transactions` 是 `Sql.transaction` 成功提交的累计数量，覆盖后台 control、heartbeat、permission refresh、传输与其他同进程工作。基准在测量前后读取 A/B/C 的累计值并相减，再求和；不使用 `transactions` 工作者任务数代替数据库事务数，不重置累计计数。每服请求应答时间保留，可评估边界读取的偏斜。报告保留 `db_deadlock_retries`、worker errors、queue rejections、quarantine 以及最终滚动性能分位数。

业务标准化指标包括每个成功接受输入事件的 DB 事务数、每 1,024 FE 实际输出的 DB 事务数。读取窗口包含边界采样、控制/心跳的不可避免开销，固定事件与持续窗口同时报告；这些指标不是某个单独内部方法的独占计数。

主路径 `counter_end` 在120秒持续阶段结束后、随后 `conservation` 排空之前采集。其事务/语句计数比较的是相同240次输入的窗口成本，尚在途的尾部工作不计入该窗口，不能称为所有资源完整生命周期的总事务数。窗口外排空仍逐项证明最终守恒，吞吐仅使用窗口内实际输出量。背压场景的恢复位于 `counter_end` 之前，计数另包含恢复和排空；不得直接混用两类窗口。没有额外的排空后总计数证据时，完整生命周期成本保持未测，不反推补值。

SQL 语句事件尝试从下表读取累计值：

```sql
SELECT EVENT_NAME, SUM(COUNT_STAR), SUM(SUM_TIMER_WAIT), SUM(SUM_ERRORS)
FROM performance_schema.events_statements_summary_by_account_by_event_name
WHERE USER = 'ct_dev' AND EVENT_NAME LIKE 'statement/sql/%'
GROUP BY EVENT_NAME
HAVING SUM(COUNT_STAR) > 0
ORDER BY EVENT_NAME;
```

观察器使用既有隔离开发容器的 root 账户执行只读 SELECT。现有三服测试 SQL helper 使用 `ct_dev`，若直接复用就会污染被统计账户；本脚本没有复用这个账户。统计限于 SQL statement 事件，包含重试、SET/COMMIT 等，不计 `statement/com/*` 的 prepare/execute 协议事件，因此不能称为 JDBC 网络往返数。

`ct_dev` 账户统计覆盖所有使用此账户的 JVM，包括端口 25578 的 `dev_perf_v1` 服务。报告记录其他有效 backend 会话；有额外负载时账户级语句数不能单独归属于三服测试。脚本检查现有 performance_schema、consumer、statement/sql instrumentation 和已存在的账户计数；若不支持则明确“未测”，不修改数据库监控配置。

旧基线没有 WAL 调用/耗时、codec 调用/耗时以及 SQL 单语句计时的应用级 instrumentation，报告明确这些项目未测。`db_transaction_ms_*` 是现有事务耗时滚动分位数，不等于单语句或独占 worker CPU 时长。不得从 SQL 总计时或 E2E 扣差推测 WAL 耗时。

## 守恒、背压与失败现场

每路累计真实接受量、真实提取量，每次提取后立即验证输出没有超过输入。预热、低流量和持续测量之间排空；测量结束继续实际提取直到以下条件同时满足：

1. 累计接受 FE 等于累计真实提取 FE。
2. 该路源与目标的本地 `txFE`、`rxFE` 均为零。
3. 该测试独有频道的 SQL pool 为零，SQL allocation `remaining` 在后续 checkpoint 对齐后为零。

SQL allocation 可能暂时镜像本地 receive credit；WAL/checkpoint 也不是独立可相加的物理库存。报告分别保存 SQL pool、allocation remaining 和本地缓冲，只检查它们最终为空，不把三者相加形成“总资源”。预热、测量和排空事件分开存储，实际守恒检查使用同一路累计的业务接受/提取量。

背压阶段预热排空后继续输入 90–120 秒，暂不外部提取，使接收容量/credit 上限发挥作用。随后保留安静窗口：接收缓冲非零且稳定、SQL pool 仍有未配送 FE 才判定已观察到背压。恢复阶段停止新输入，执行真实提取，记录恢复首次输出时间和排空耗时，最后检查完整守恒。仅观察到暂时积压不等于背压通过。

功能失败还包括超时、累计计数倒退、JVM PID 改变、持续接收端零输出、worker error、queue rejection 或 quarantine。成功排空后关闭自己设备并拆除自己的空方块与 vanilla load tickets；失败时关闭 FE 模式，保留方块、资源与票据供诊断，不销毁已接受资源。频道与 SQL 审计历史保留，不直接 DELETE 后端记录。

## 回归判定与报告使用

自动比较要求 schema 与全部 `conditions` 相同，逐场景比较重复样本的中位数：实际提取 FE/s、每接受事件的 DB 事务、每 1,024 输出 FE 的 DB 事务，以及隔离低流量全部输出上界 p95。默认允许相对变化 10%；低流量还要求绝对上升超过 10 ms 才自动标记。可用 `--max-regression-percent` 调整阈值。自动标记是一项调查信号，不提供统计显著性结论。

功能失败报告仍可作为现象证据，不能称为已通过的性能基线。比较时应同时列明：输入尝试/接受事件是否相同、实际输出守恒、每端实际服务、观察器滞后、RCON 误差范围、事务/语句统计范围、进程/世界/SQL 身份以及未测项目。label 和 git HEAD 不足以证明 JVM 中已加载的代码版本；旧 harness 无运行时代码摘要，应由启动记录与冻结的源码/构建记录补足。

本基准与 100/500/1000 端点的 `scripts/performance-test.py` 互补。后者测单服大规模加载/活动端点负载；本脚本测统一外部观察器下同服、跨服和混合路径的真实接口业务、后端成本与公平性。二者不可并发运行后再将共享账户 SQL 语句数归属于任意一个测试。

## CPU、堆、GC 与 FD 的只读旁路观察

`scripts/optimization-monitor.py` 独立于冻结的基准驱动，可在同一负载期间由操作者启动：

```bash
python3 scripts/optimization-monitor.py --self-test
python3 scripts/optimization-monitor.py \
  --label baseline-87bf217 --seconds 6000 --interval 5
```

改后使用同样采样参数与对应 label。监控初始仅对每服执行一次只读 `ct_test pid`，以定位真实 RCON JVM；后续不调用测试业务命令或 SQL，不启动 JFR，不启停服务器。每五秒并行采样三服，执行有界的 `jstat -gc` 与 `jstat -gcutil` 读取，并保存每条命令的原始输出、返回码与观察时间区间。每条 jstat 默认超时两秒；缺工具或读取失败时对应堆/GC 数据保持未测，不推算补值。短暂的 jstat 工具进程及文件读取有观察器开销，前后测试应一致。

监控输出 `reports/optimization-monitor-*.json` 与同名 CSV。CSV 每轮落盘，JSON 每六轮及退出时更新；Ctrl-C 保存已有数据。`/proc/PID/stat` 的 starttime 同时验证 PID 未被复用，进程消失或身份变化即停止并保存失败。报告列明实际采样间隔和持续时间，可辨认负载下超过五秒的读延迟。

| 字段 | 真实含义 | 不可据此声称 |
| --- | --- | --- |
| CPU seconds / process percent | `/proc` 累计用户与内核 CPU 时间差；一个核的 100%，可超过 100% | 独占 mod CPU、单线程占用或整机使用率 |
| RSS / VmHWM | 整个 JVM 的当前驻留内存 / 自启动以来驻留高水位 | Java 对象堆用量或本阶段 RSS 精确峰值 |
| heap used / committed | `jstat -gc` 中 S0/S1/Eden/Old 的使用与容量总和，原单位 KiB | 分配率、对象保留量、原生内存或精确瞬时峰值 |
| YGC/FGC/CGC 与对应 time | jstat 可用的累计收集次数与累计耗时差，时间单位秒 | 单次 pause 分位数、STW 时间分布或整服 MSPT |
| fd_count | `/proc/PID/fd` 中当前描述符数量 | 全机器 FD 使用或仅 mod 的文件描述符 |

汇总中的 `observed_max` 只是五秒采样看到的最大值；阶段间比较应按基准时间窗口切片，保留实际覆盖范围。监控包含微秒级 UTC 与本机 Python 单调时钟值，驱动当前 UTC 起点仅精确到秒，按 UTC 对齐存在至多约一秒的阶段边界误差。后启动的旁路监控没有之前阶段的数据，不能补称完整首轮结果。

完整循环及全部扩展工作的整服 wall MSPT 暂未测。若后续单独运行全服 JFR 作诊断，应保存新的诊断条件与时间窗口；不能将后来 JFR 的 tick/pause 数值补入未开启 JFR 的基线，或把 mod 自身 `tick_ms_*` 替换成整服 MSPT。下面的原生已记录 tick 工作均值另有范围限制。

## Minecraft 原生 tick 工作均值的补充观察

MC 1.21.1 / NeoForge 21.1.252 的本地源码与 javap 均确认以下真实 API：

| 类与方法签名 | 单位及语义 |
| --- | --- |
| `MinecraftServer.public long getAverageTickTimeNanos()` | 最近 `min(100,max(tickCount,1))` 个已记录 tick 的算术均值，纳秒；除以 `1_000_000.0` 得毫秒 |
| `MinecraftServer.public long[] getTickTimesNanos()` | 原生 100 槽已记录 tick 工作耗时环，纳秒；不能修改返回的内部数组 |
| `MinecraftServer.public float getCurrentSmoothedTickTime()` | 毫秒，`0.8 × 旧值 + 0.2 × 新值` 的指数平滑值，与 100 tick 算术平均不同 |
| `MinecraftServer.public ServerTickRateManager tickRateManager()` | 取得服务器 tick rate manager |
| `TickRateManager.public float tickrate()` | 配置的目标 ticks/s；不是实测或瞬时 TPS |
| `TickRateManager.public float millisecondsPerTick()` / `public long nanosecondsPerTick()` | 配置目标周期，分别为毫秒/纳秒；不是实际工作耗时 |

版本来源为 `build/moddev/artifacts/neoforge-21.1.252-sources.jar`：

- 整包 SHA-256：`005619490960aa2e099911bbc562af5cb67505770436a8ed1e63fe14d668e8fc`。
- `net/minecraft/server/MinecraftServer.java`：第 912–944 行记录 tick；第 1716–1729 行提供均值、平滑值和数组；条目 SHA-256：`b906c6597095e206ade6a9db34f76993f667bdf2bfacaeca793ba9ce14e568ed`。
- `net/minecraft/server/commands/TickCommand.java`：第 58–59 行将纳秒格式化成一位小数毫秒，第 70–97 行执行只读 `tick query`；条目 SHA-256：`c9fe049c16f424ac507b0c47b43cfe5eb10566e85d348104a01e3b073a7d0ef6`。
- `net/minecraft/world/TickRateManager.java`：第 15–29 行提供目标速率与目标周期；条目 SHA-256：`c740d68d1247c842c4f1b78779d5817aa5cab6ae4ae00bd0052a0ba5381c927f`。

该原生均值的计时从 `tickServer` 开始，包含 `ServerTickEvent.Pre`、世界 tick、服务器状态更新及 autosave。NeoForge 在 tally 完成后才触发 `ServerTickEvent.Post`，因此 Post 回调、循环等待和部分外层任务不在该平均内。本 mod 的 `RuntimeEvents.tick` 使用 Pre，核心 mod tick 被包含；bulk 测试 fixture 使用 Post，其耗时被排除。建议新增状态字段命名为 `mc_recorded_tick_ms_avg100`、`mc_target_tickrate`、`mc_target_tick_ms`，同时保留这一范围说明。

只读 RCON `tick query` 的实际回复例如：

```text
The game is running normally
Target tick rate: 20.0 per second.
Average time per tick: 0.3ms (Target: 50.0ms)
Percentiles: P50: 0.3ms P95: 0.4ms P99: 1.1ms, sample: 100
```

回复的均值和分位数属于查询时的原生 100 tick 窗口，按一位小数毫秒舍入，误差约 ±0.05 ms。它不是整阶段全部 tick 的聚合，更不是所有任务与插件的完整 wall tick；`Target tick rate` 只表示目标速率，不报告实测 TPS。

独立工具 `scripts/optimization-tick-monitor.py` 每十秒并行查询三个 JVM：

```bash
python3 scripts/optimization-tick-monitor.py --self-test
python3 scripts/optimization-tick-monitor.py \
  --label baseline-r3 --seconds 6000 --interval 10 \
  --coverage-note 'Baseline third repeat only; earlier repeats MC tick data UNMEASURED'
```

只调用初始 `ct_test pid` 和周期性的 `tick query`，不调用 reset、rate、freeze、sprint、输入或数据库变更。CSV/JSON 保存原回复、UTC、请求/应答单调时钟区间、实际进程身份与源码 artifact 摘要。Ctrl-C 保存已有数据；PID 消失/复用或无法解析的回复会留下失败证据。工具不自行启用 JFR 或修改运行中的驱动/GC 监控。

如果基线第三轮才开始该采样，第一轮与第二轮的原生 tick 均值必须标为未测；只比较实际覆盖且负载阶段对应的窗口。每十秒查询在目标 20 ticks/s 时取到的是最近约五秒的窗口，并未完整覆盖阶段全部 tick。汇总的 `observed_mean_of_tick_window_means_ms` 是已查询窗口均值的平均，不得改称全阶段 MSPT 平均；窗口分位数也不能合并冒充全阶段 p95/p99。

## 首轮87bf217历史基线与离线比较

基线 [optimization-baseline-87bf217-20261006T090251Z-7859e9.json](../reports/optimization-baseline-87bf217-20261006T090251Z-7859e9.json) 已完成九个样本，`passed=true`，约 2,949 秒。每条路径每轮 40 笔低流量探测、30 秒预热、120 秒持续负载，持续阶段固定 240 个 32,000 FE 输入全部成功接受。下表的低流量值是“完整实际提取”的 RCON E2E **上界**毫秒；每轮下界与原始事件保存在报告中。

| 路径 | 重复 | p50 上界 ms | p95 上界 ms | p99 上界 ms | steady DBtxn / 240 输入 | steady SQL events / 240 输入 |
| --- | --- | --- | --- | --- | --- | --- |
| same | 1 | 2740.84 | 2933.39 | 2939.46 | 3735 | 37120 |
| same | 2 | 2744.40 | 2866.16 | 3340.94 | 3714 | 34735 |
| same | 3 | 2735.04 | 2845.32 | 2935.75 | 3682 | 36589 |
| cross | 1 | 2749.86 | 2936.07 | 2949.77 | 3653 | 35885 |
| cross | 2 | 2745.21 | 2846.64 | 2937.47 | 3657 | 35774 |
| cross | 3 | 2743.41 | 2866.96 | 2934.22 | 3674 | 35192 |
| mixed | 1 | 1930.39 | 2266.54 | 3467.80 | 3614 | 31657 |
| mixed | 2 | 1835.37 | 2912.35 | 3402.30 | 3643 | 31935 |
| mixed | 3 | 1932.76 | 3054.52 | 3302.46 | 3434 | 29836 |

每类三轮分位数的中位数分别为 same `2740.84/2866.16/2939.46` ms、cross `2745.21/2866.96/2937.47` ms、mixed `1930.39/2912.35/3402.30` ms。固定 240 输入的 DB 事务中位数为 `3714/3657/3614`，SQL statement events 中位数为 `36589/35774/31657`。这些是既定低频与持续输入条件下的结果，不是峰值容量。

九轮 worker errors、queue rejections、quarantine 均为零，观察器无迟到轮次或饱和。mixed 第一轮记录一次 `db_deadlock_retries` 和一次 SQL statement error，随后成功恢复；不能将它写成“所有 SQL 错误为零”。每轮排空后累计真实接受/提取相等，SQL 与本地缓冲分别为空。重新核对原始事件账本，全部路径包含低流量、预热、持续与排空的输入/输出共 `86,768,640 FE`，相等。

mixed 每轮低流量 A/B 各实际接收 20 笔，即各 20,480 FE；三轮持续阶段 A/B 的输出总量分别为 `11,648,000/11,072,000 FE`，两端每轮均有持续服务，最长未服务间隔约 3.50 秒。持续窗口内尚未提取的尾量在后续 drain 中实际提取，不能因 120 秒窗口输出略低于输入就判定丢失，也不能把 drain 吞吐混入 steady。

此FE主路径驱动共有七个端点，均位于各自服务的单个相同坐标区块内，使用 overworld。`NeighborPump.tick` 明确跳过相邻 `TesseractBlockEntity`，因此相邻布置不会绕过SQL路径。该驱动自身不覆盖同服不同chunk、跨dimension、真实chest/机器容器或物品/流体；后续拓扑、箱子和混合资源驱动分别记录这些场景，不能将它们的结果归入本驱动计时样本。

离线工具 `scripts/optimization-compare.py` 只读取文件，不导入或访问 RCON、SQL 或进程。它可以保留多个版本及失败报告：

```bash
python3 scripts/optimization-compare.py --self-test
python3 scripts/optimization-compare.py \
  --baseline reports/optimization-baseline-87bf217-20261006T090251Z-7859e9.json
```

后续传入 `--batch`、`--fast`，或重复使用 `--report NAME=PATH`，并可用 `--output reports/optimization-comparison.json --csv reports/optimization-comparison.csv` 导出完整聚合。没有提供的 batch/fast 保留为 `not_run/UNMEASURED`；指定文件缺失、失败、尚未完成或未完成清理的状态与原始原因都会保留，不填入成功性能值。默认退出码表示聚合工具是否运行；`--strict` 对已指定的失败/不完整报告及检测到的回归返回非零。

工具逐轮重新计算低流量上下界 p50/p95/p99，核对 probe 数、固定输入次数、实际事件账本、接收端服务与独立空库存检查，再求三轮分位数中位数。各路径复用同一频道，`conservation.accepted_FE` 跨重复累计；聚合仅取该路径最新累计值，与独立事件账本相核对，绝不将第一/二/三轮累计数再次相加。失败轮原始证据保留，但不混入“已完成有效重复”的统计。

自动比较要求条件、拓扑和完整重复一致。SQL 语句来自账户总计，若任一报告存在其他或未知的有效 backend 会话，其变化仅列为诊断，不自动归因或标记 SQL 性能回归。错误总计与每轮详情同时保留，避免中位数为零掩盖少量恢复事件。

## 单 perf 服务的规模采样补充

既有 `performance-test.py` 的 100/500/1000 端点报告没有保存测量起点的完整 DB counters，不能从最终 `db_transactions` 值直接重建每个 OFF/ACTIVE 阶段的事务差。可旁路读取：

```bash
python3 scripts/optimization-scale-monitor.py --self-test
python3 scripts/optimization-scale-monitor.py \
  --label baseline-scale-late --seconds 1800 --interval 2 \
  --coverage-note 'Late baseline scale sampling; earlier phases UNMEASURED'
```

该工具固定开发 RCON 25578，初始 `ct_test pid`，之后每两秒只读 `status` 与 `bulk-status`。原文、全部数值、两个命令各自的请求应答区间都保存；每次读取 `/proc`，默认每十秒保存 jstat 的原始堆/GC 结果，可用 `--jstat-every 0` 禁用。它不切换 bulk-active、reset、不创建业务资源或故障，不更改正在运行的性能脚本。

以 bulk `count/registered/bound` 与 `active_endpoints` 推断 `OFF_observed/ACTIVE_observed/setup_or_transition`；`tick_ms_samples` 下降只说明 reset 在两个观察点之间发生。按观察到的稳定规模/状态与 reset 标记拆分子窗口，再计算这两个真实采样点之间的 DB transactions、deadlock retries、worker errors、queues 与 fixture 累计差。状态推断不是独立的权威 bulk-active 标志，也不自动证明完整 120 秒阶段边界。

晚启动的工具可以补到 500/1000 的实际可见子区间，之前的 100 端点阶段或未覆盖首尾仍须标未测。JSON 每十秒保存，Ctrl-C/结束时生成 JSON/CSV；汇总明确实际观察秒数及 RCON 边界区间，不把子窗口差值外推成未测全窗口。`tick_ms_*` 仍是 mod 自身 histogram，不是完整 Minecraft wall MSPT。

## 最终修复版本的补充验证口径

旧核心4cfff0a的27窗口保持原样。75392af修复真实MySQL死锁和清洁OFF调度后，另以新世界重新执行；所有新模式使用单个工作负载RCON观察器，没有并发RCON/tick/SQL/JFR旁路。原始87bf217由已经冻结的classes/resources启动，新模式由当前固定类文件启动，记录实际modFolders摘要；不能用当前checkout HEAD冒充已加载版本。源类文件、普通资源、SQL政策和外部输入事件保持对应记录。

箱子补充只执行实际原版容器的32个普通stone，不添加追踪组件。它不属于30/120秒稳态基准。首轮每布局十次的原版尝试在第二笔超时，保留失败现场；最终同条件比较为每布局两次，共六次，不给总体p95/p99保证。源容器扣除、目标容器增加均以同一Python时钟的保守区间计算；验证本地缓冲与SQL剩余各自为空，不能将SQL/WAL重复记账。任何不确定失败保留资产与原始应答/SQL快照，不补发不清空。测量成功仍不表示世界已持久化。

规模复测沿用x30357、z0、32×32范围和六个已加载区块，100/500/1000分散于最多四个256端点频道，五秒预热、单个120秒窗口。此脚本和只读2秒旁路的误差范围分别保存，原版缺失的首次计数不补填。500/1000失败e4057a5报告、1305掩盖1213的实际InnoDB证据及错误解析修复保留，不能从最终报告中删除。

## 最终串行套件与源码归属

`68f32db` 核心的实际构建摘要在 `reports/optimization-artifact-ready-final.json`。基础启动profile、已运行的loopback后端和明确接受EULA的隔离环境准备完成后，正常停止所有测试JVM：

```bash
scripts/gradle-dev.sh createServerALaunchScript createServerBLaunchScript createServerCLaunchScript createServerPerfLaunchScript
python3 scripts/optimization-final-sequence.py --stage current \
  --original-sequence-report reports/optimization-final-sequence-original.json --execute
python3 scripts/optimization-regression-suite.py --mode fast --execute
python3 scripts/optimization-regression-suite.py --mode legacy --execute
```

套件拒绝已有同名证据/已用世界，重新执行时要显式归档报告并选择独立测试环境；不会删除旧世界或清理失败资产。两个regression模式使用同一JAR并经正常停机换配置，不是旧二进制混跑。源码/JAR必须匹配声明的核心清单；只改文档的git提交不等于新的Java运行版本。启动器冻结实际classes/resources与参数文件，报告保存PID、会话和摘要，但没有class-loader级源码证明。

主比较套件先执行真实箱子同服/跨服/混合各两笔，接着压力两种布局各三次，最后仅合批/合批加本地路径各九个120秒样本与每样本40次probe。性能回归与功能失败分别保存，套件的procedure_completed不能解释成全部性能目标通过。正式三服窗口只有一个RCON工作观察器；旁路规模/JFR方法是独立实验，不在此期间运行。

重跑原版应使用新的干净仓库副本，先在原始87bf217构建和冻结三份基础launch，再切到本轮工具分支（不要在有未提交修改的工作区切旧版本）。使用 `freeze-dev-launch.py build/moddev/runServerA.sh` 等产生实际路径，按A/B/C键写JSON manifest。原版套件必须显式提供 `--original-launch-manifest`，不把当前classes冒称baseline。迁移、Java/NeoForge与外部依赖按原记录固定，清洁停机后才换源码/配置；旧固定UUID目录只是本环境证据，不是新机器需要照搬的路径。

新测原版入口生成 `reports/optimization-final-sequence-original-68f32db.json`，current须以 `--original-sequence-report` 显式选择它；上面的旧文件名仅指本轮实际完成的基线。入口核验完成状态、声明的原版修订、两个唯一阶段、30/120秒三重复和每份子报告SHA-256，禁止静默退回已有历史文件。离线元数据/错误拒绝测试为 `python3 scripts/optimization_sequence_input.py`，本轮实际旧基线核验记录在 `reports/optimization-baseline-selection-validation.json`。本轮计时进程已载入修正前Python模块，保存了修正前脚本摘要；没有重启计时或改变游戏核心/负载。

物品组件/流体/FE同频道补充使用 `optimization-resource-mix.py`。每个稳态窗口固定一次32+32个带两种稳定CUSTOM_NAME的石头、240次FE/水输入尝试；它分别保存各资源真实接受/拒绝、源实际扣除、外箱实际输出、观察器成本、主窗口成本和完整尾部排空成本。组件表示工作负载差异，不作为追踪ID。若FE/流体部分拒绝，版本间实际输入不同，必须明确列出，不能只因attempts相同便声明业务量相同。原版扫描的长等待和120秒窗口内零ITEM输出不隐藏到延长后的窗口。

`optimization-extra-sequence.py --execute --original-launch-manifest <实际manifest>` 先做一个不计性能的native组件smoke，再顺序测原版/仅合批/快速三配置的mixed资源场景、最后故障和回退。`--wait-primary` 仅读取已保存主报告并等待正常停机，不向正在计时的服务器发RCON/SQL。失败保持独占资产，后续步骤停止，先读原始报告再决定修复；不能以重播命令作为通用恢复。

快速模式回归套件最后调用 `optimization-restart-fallback-test.py --execute`：仅在本套件已有的隔离三服/同一存档运行，分别保留75FE LOCAL与61FE共享余额，正常停机并以同一冻结类文件改为false,false，随后验证原凭证与真实136FE领取，再恢复true,true正常重启检查重复领取为零。它不删除世界、强杀、自动恢复失败配置或重试不确定提取。`--self-test` 只验证离线格式/账本辅助函数，不能列为实际回退通过；实际结果另存独有 `optimization-restart-fallback-68f32db-*.json`。


## 正常重启回退与两次观察器失败

最终核心68的完整回退报告为 `reports/optimization-restart-fallback-68f32db-20261006T195817Z-df658dc1.json`，父控制器 `reports/optimization-final-fallback-controller-68f32db-58fcc66e.json`。同一官方构建JAR、同一server/world身份和冻结class/resource选择，经过正常停服的true/true→false/false→true/true三个启动会话。两个新频道各实际输入189FE、输出189FE，原allocation和独立61FE allocation的ID保持可追踪，重复提取为0，最后SQL pool/remaining及本地/WAL额度为空。此项证明正常停止的配置回退，不证明任意外部机器原子保存或故障强制退款。

第一次原始测试因TSV响应整体strip丢失末尾空HEX载荷列失败；只发生一次128FE输入，没有提取或切配置。第二次修复测试已经完成新两频道378FE输出，但SQL检查点先读到8、WAL稍后读到10，被静止观察器错误拒绝。两次失败与原父 `optimization-extra-sequence-68f32db.json` 的FAILED原字节保留。最终修复仅在初始完整状态收敛后，对“同端WAL版本领先先前读取SQL检查点、其余完整资产/业务ID条件均通过”的读偏斜重置连续静止计时，总期限固定；真实数量/凭证/ID差异仍立即拒绝。所有真实读视图都保留，测试不会把修正的内存分类视图当成落盘证据。最终实测观察到一次该类重试。

ROOT在第二轮停服后核对新两频道有效余量0及原128FE仍完整，持有停服锁后仅恢复两个开关的原始字节，再用新ID完成第三轮测试。原128FE的SQL LOCAL与WAL是同一资产镜像，未计成256、未重放或提取；结束后的独立只读证明为 `reports/optimization-restart-fallback-after-corrected-audit.json`。正常回退测试运行后，控制器正常停止全部三个JVM。历史失败控制器原源码与第二轮实际运行的观察器源码在证据包 `reports/raw/` 保留，未继续使用已失效的第一次恢复入口。

实际执行：

```bash
python3 -B scripts/optimization-restart-fallback-test.py --self-test
python3 -B scripts/analysis/run-fallback-final-68f32db.py --execute
python3 -B scripts/analysis/audit-fallback-original128-68f32db.py \
  --output reports/optimization-restart-fallback-after-corrected-audit.json
python3 -B scripts/optimization-regression-suite.py --mode legacy --execute
```

最终控制器是本次失败现场专用复现配方，要求已完成的三份ROOT资产/配置门与停止的隔离68世界，不是运营服恢复工具。普通新环境使用 `optimization-regression-suite.py --mode fast --execute` 创建独立开发世界并执行完整阶段；两种入口均拒绝覆盖已有带版本报告，重新复现应使用新的隔离副本，不清理用户世界。只读audit输出也拒绝覆盖：另一次核对需另给一个新 `reports/*.json` 路径。
