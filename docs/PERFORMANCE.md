# 性能实测、指标与调参

本项目没有“零影响”或固定支持 1000 端点的生产容量承诺。报告保存原始实际数字；短窗口、单种 FE 负载和本机后端不能外推到大型工厂、多 JVM 热点物品组件或高延迟网络。

## 复现方法

```bash
scripts/dev-backends.sh
python3 scripts/setup-dev.py --accept-eula
scripts/gradle-dev.sh createServerPerfLaunchScript
scripts/start-dev.sh perf
# 另一终端：
python3 scripts/performance-test.py --label experiment --seconds 20
```

使用干净的独立测试世界和独立稳定 server.id；不要复用旧测试世界后假装只有新登记的设备。脚本拒绝超出开发群组，在相同已加载区块下分别测 OFF 和 active，100→500→1000 个真实设备，每种状态预热五秒、观测二十秒。四个频道各最多 256 端点；分布分别为 `[100,0,0,0]`、`[256,244,0,0]`、`[256,256,256,232]`。已注册、已加载和活跃端点分别记录，三者不能混用。

机器为 AMD EPYC 9V74，容器可用五个逻辑 CPU，MemTotal 18440136 KiB；Temurin 21.0.8+9，服务端 `-Xmx2G`，Minecraft 1.21.1/NeoForge 21.1.252。MySQL 8.4.7 默认配置、Redis 7.4.6 本机 Docker loopback，没有注入网络延迟。最终源码的结果见 `reports/performance-final.json`；每个 JSON 保存环境、时长、吞吐、队列和分位数，运行完成后 `passed` 必须为 true。

负载生成器每 tick 最多十六次真实 FE 能力调用，发送端输入 1000 FE、接收端最多提取 32000 FE；输入上限由生成器调用频率和轮转决定，并不是后端处理极限。吞吐用实际接收端提取量/实际秒数计算。生成器耗时单独记录 `fixture_ms_per_tick`，不计入模组 Runtime 的工作耗时。即使同服端点，也走相同 SQL 权限/所有权路径。

加载由测试 fixture 的 vanilla 票据保持，OFF/active 时区块和设备相同；它们不是本模组配额实现。没有其他工厂机器。因此本实验测量 A：本模组额外工作；B：强制加载后其他机器持续运行的额外成本**未测**。不能将 B 隐藏，也不能用本实验解释实际大型工厂的总 MSPT。

## 保存的优化证据

最终复测的已注册/已加载/活跃设备数分别全部达到 100、500、1000，设置阶段和测量窗口均没有任务错误或队列拒绝。下表只代表该真实 FE 负载、单 Minecraft JVM 和本机后端；每个 active 窗口为二十秒，数字来自 `reports/performance-final.json`。

| 活跃端点 | 实际接收 FE/s | 主线程 p95 ms | 主线程 p99 ms | 同加载 OFF p95 ms | SQL 事务 p95 ms |
|---:|---:|---:|---:|---:|---:|
| 100 | 165798.90 | 0.454502 | 0.944657 | 0.208773 | 9.909885 |
| 500 | 140699.37 | 0.558869 | 1.044417 | 0.177937 | 9.04951 |
| 1000 | 138949.45 | 0.701483 | 1.096997 | 0.182784 | 8.127553 |

1000 场景结束时后台队列仍有 94 项有界积压；累计 SQL 死锁重试为 71 次，均按重试路径恢复。零任务失败不表示没有锁争用，也不表示长期负载必定不会达到背压。

库存功能之前的上一轮最终复测保留为 `performance-pre-stock.json` / `reports/raw/final-pre-stock.jfr`；本次使用新独立 `dev-perf-stock-final` / `world-stock-final` 复测。后续调整库存页面的方向提示/按钮及开发客户端截图等待；服务端 Runtime、SQL/WAL、配额和 FE 能力实现不变，class 比对见 `launch-class-parity.json`。

绑定防护修复前的复测单独保留为 `performance-pre-binding-fix.json` 和 `reports/raw/final-pre-binding-fix.jfr`，其中设置阶段有七次错误，不能用它代替上述最终结果。

`performance-before.json` 保留优化前的 100/500 实测；当时 500 设备仅 386 活跃，二十秒窗口中出现 1527 次队列拒绝和 1 次任务错误（累计 4 次），1000 的设置未在超时内完成，不能补估算数值。`performance-after.json` 保存首轮优化后的完整 100/500/1000 测量。源码随后加入相邻自动交换、票据预算和绑定期间输入暂停，因此最终结果另外复测，不能把旧结果冒称为最终代码。

真实 JFR 保存于 `reports/raw/before.jfr`、`after.jfr`、`final.jfr`；优化前执行样本导出为 `before-samples.txt`。通过 JFR/SQL 队列观察减少了持有无关 session/channel 行锁的 joined FOR UPDATE、未变更 WAL 重写和串行 journal 文件锁，批量流水 outbox 标记，按注册截止时间调度并保留管理队列余量。优化后并没有证明所有指标都更快：不同规模的吞吐和分位数应按 JSON 逐项比较，不能只选最大 FE 数值。

```bash
scratch/jdk/jdk-21.0.8+9/bin/jfr summary reports/raw/final.jfr
scratch/jdk/jdk-21.0.8+9/bin/jfr print --events jdk.ExecutionSample reports/raw/final.jfr
```

## 指标的准确含义

- `tick_ms_*`：Runtime 主线程工作滚动最多 2048 样本；不包括所有 Minecraft/其他模组工作，不等于整服 MSPT。
- `db_transaction_ms_*`：Sql.transaction 实际耗时，包含连接/重试及事务中的语句；`db_deadlock_retries` 记录重试。
- `sql_ms_*`：历史名称，实际是后台任务/批次总耗时，可能含 WAL；不能解释为纯 SQL 延迟。
- `delivery_ms_*`：接收批次开始到本地额度应用的延迟，**不是**源外部机器抽取到目的机器保存的完整端到端延迟。完整端到端外部交付测量仍待加入。
- `worker_queue`、`queue_rejected`、`errors`、`quarantined`、`actual_tickets`、`transactions`：当前队列/累计计数；测试窗口用差值，启动阶段错误不能从报告中抹去。

票据恢复/安装会触发 Minecraft 区块加载，单次可超出 2 ms 软预算；初次恢复不是稳态传输数据。默认每 tick 只处理两个票据变更；数据库/Redis 故障下撤销自己的实际票据优先保证失效边界。改变该预算会影响恢复延迟，不能承诺票据本身零主线程开销。

## 默认预算与调参

配置示例包含每 tick 16 端点检查、64 完成项、16 个重序列化栈、2000 µs 软预算；200 ms 批次、每批最多八个发送记录、128 后台队列、4 SQL 连接。空闲轮询下降到两秒，达到容量/队列阈值返回零或剩余形成背压。物品九个 TX 槽、流体四个 TX 槽、化学品四个 TX 槽，接收凭证上限 64；FE 默认 2000000、EU 默认 16777216。

热点频道的 SQL 余额锁、不同组件种类的序列化/WAL 和记录数量通常比单个 FE 数值更重要。先看队列、实际事务、数据库分位数和 JFR，再改预算；不要通过无限队列掩盖不足。所有这些启动配置需要重启，群组配额/频道限制以权威政策为准。

每服历史默认 500000 条准入，终态保留三十天。持续高 TPS 会较快达到该上限并产生背压；本次几分钟测量没有验证三十天持续容量或自动完整归档。未解决隔离、活资产及 tombstone 不能清理以强行恢复吞吐。生产需结合磁盘、备份和保留策略决定容量，并演练暂停及归档。

大型不同组件、热力延迟振荡、多子服 1000 端点热点频道、网络延迟/丢包、长期数据增长与实际其他工厂机器负载均尚未压测。
