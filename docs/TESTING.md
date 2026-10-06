# 实际测试与复现

## 本轮频道合批与本地调度验证（2026-10-06）

当前源码 `68f32db` 已完成68项单位/性质/真实后端测试（35项单位/性质、33项真实后端；失败、错误、跳过均0）及13项基础原生GameTest。XML/HTML在 `reports/optimization-tests-ready-final/`，命令、源码/JAR摘要在 `reports/optimization-artifact-ready-final.json`，日志 `logs/optimization-build-ready-final.log`。LocalRoomTest 验证快速空间探测的凭证/零额边界；ChannelCoordinatorTest 新增 pending 查询和首次在途信号测试，并在 partial-batch、150组随机模型中逐步核对查询结果。

同一修订八种可选组合全部通过，共132项必需原生执行（组合之间包含重复测试，不是132个独立测试）：`reports/compat-matrix-68f32db.json`、`logs/optimization-matrix-68f32db/`。官方冷安装的同一JAR完成实际1234FE输入/输出，Java正常退出0：`reports/packaged-smoke-68f32db.json`、`logs/optimization-packaged-68f32db.log`。925/753/4cf/e405及下方客户端报告均是注明版本的历史实际运行，不能替代当前修订的性能或三服故障复测。

当前规模六窗通过：100/500/1000真实端点，各OFF与ACTIVE120秒、五秒预热、一次重复，业务与监测器正常退出；`reports/performance-opt-fast-68f32db.json`、`reports/optimization-scale-comparison-68f32db.md`。每频道最多256端点，1000档分为四频道；没有称为单频道1000端点。ACTIVE主线程滚动p95相对原版仍有回归，首次观察器在输入前启动失败的报告保留。

三个真实JVM中的普通箱子六次探测和压力六窗均通过，原始文件路径及SHA见 `reports/optimization-container-comparison-68f32db.json` 与 `reports/optimization-pressure-comparison-68f32db.json`。箱子源实际扣除、目的外箱实际接受、SQL余额/独占remaining与本地余量独立核对；压力包括满载后恢复和热点/低流量频道共同竞争。计时是容器/能力实际接受，不表示世界立即存盘。

最终原版/仅合批/快速各九窗均实际完成，30秒预热、120秒观察、每窗40探测、三重复；只有一个RCON工作负载观察器。三个profile的业务核对通过，严格性能比较退出1并保留SQL/WAL等回归。完整重复、上下界、资产静止屏障及目标未达在 `reports/optimization-comparison-68f32db.json/.csv/.md`，不能用“功能通过”概括为所有性能目标达成。

同频道原生混合smoke已实际运行：两种不同CUSTOM_NAME的32+32个stone源箱自动抽取并进入实际目标箱，64,000FE与2,000mB水能力实际输入/提取，三个资源的SQL/本地零余量独立核对；报告 `reports/optimization-resource-mix-smoke68-20261006T185222Z-877b8b.json`。它的稳态配置仅1秒、一次重复，属于命令/组件/资产核对，不算正式性能窗口。

正式同频道混合原87/仅合批68/快速68各三次30秒预热、120秒观察，九窗均真实执行且passed。三份子报告是 `reports/optimization-resource-mix-original87-20261006T185321Z-8c23fc.json`、`reports/optimization-resource-mix-batch68-20261006T190206Z-258fe6.json`、`reports/optimization-resource-mix-fast68-20261006T191056Z-43958a.json`，SHA与 `reports/optimization-extra-sequence-68f32db.json` 的唯一引用一致。每稳态窗两种稳定CUSTOM_NAME石头各32个，经实际源箱/外箱；FE与水各240次原生能力输入，按独立单位账本和最终SQL/本地零余量核对。仅合批两种组件输入→外箱完整接受上界中位71.097889/78.184268秒，原版29.287011/30.355341秒，严重等待回归保留；功能通过不能代替性能目标。成本窗口/源扫描等待/上下界/所有重复见 [PERFORMANCE.md](PERFORMANCE.md)。

当前68核心的fast模式（`channelBatches=true/localFastPath=true`）已结束五个独立回归阶段：

- `reports/three-68f32db-fast.json`：三真实JVM邀请/接受、FE/item/fluid守恒、A/B多发送与BOTH旧RX不回流、同区块独立票据、三服竞争两个配额以及移成员后能力关闭，套件exit0。接收缓冲合计76000 FE、144 item、6000 fluid，报告保留正RX，不将它称为全体外部提取后的零余量。两次预期配额拒绝与C末累计 `errors=2`、`db_deadlock_retries=2` 均保留，不能称全轮零错误。
- `reports/optimization-topology-final-fast-68f32db-20261006T192008Z-6be3bb.json`：不同区块、跨维度、ABC三发三收、RECEIVE→OFF→RECEIVE、空设备拆除后新ID五case全部passed。不同区块4096 FE、跨维度3072 FE均实际提取并静止核对；ABC共3456 FE，三个接收端896/1280/1280，不要求均分。独立窗口新增错误/拒绝/隔离/死锁重试为0，之前累计计数仍保留；不覆盖在途强制卸载、正余额拆除回收或任意第三方机器。
- `reports/faults-68f32db-fast.json`：五处after_send_wal/after_deposit/after_allocation/after_receive_wal/after_local_sql实际halt(97)，验证新epoch隔离、所有权保留与不按超时退款。提交后进程中断不是切断COMMIT ACK网络；没有多端点/多publication分组的部分提交halt矩阵。
- `reports/recovery-68f32db-fast.json`：正常重启主动恢复授权ticking票据，实际停止Redis撤票且保留配额，重启/FLUSHDB不删权威配额，硬kill后新epoch隔离且不恢复旧票据。
- `reports/mysql-68f32db-fast.json`：MySQL实际停止/重启，测试耗时7.918233秒；停库时实际票据0、持久槽1、新批准0，恢复票据1。故障中一次管理RCON应答0.980320ms、内容database_unavailable；故障errors=1、末尾累计errors=2均保留，不声称全0或所有断网时间边界。

这些完成阶段按运行套件的68源码/启动选择及子报告SHA归档，不是独立classloader attestation，也不能外推其他开关配置。extra父序列后来在同存档回退验证器处失败，仍保持FAILED，不能将混合子任务通过或这五个完成阶段改写为整套回归成功。

首轮回退在fast_prepare_positive_assets由strip丢失FE空HEX列而失败，尚未配置切换；`reports/optimization-restart-fallback-first-failure-audit.json` 是ROOT只读SQL/校验WAL审计，确认唯一实际128 FE输入、0输出、SQL LOCAL128与同凭证WAL镜像128，有效资产128而非256。原fixture保留，未重放或退款，不把失败改成通过。

第二轮 `reports/optimization-restart-fallback-68f32db-20261006T194856Z-b6a7c332.json` 已完成同世界正常true→false重启，新same/cross各189 FE实际输入/输出、duplicate0，但静止quiet验证跨读SQL checkpoint8与随后WAL10而失败；`reports/optimization-resume-extra-68f32db-20261006T194822Z-c221422a.json` 同样EXIT1。`reports/optimization-restart-fallback-second-failure-assets-audit.json` 确认新两频道378 FE实际输出且SQL/WAL有效余量0；`reports/optimization-restart-fallback-after-second-failure-audit.json` 确认原128仍有效128、实际输出0。这两次失败及extra父FAILED保留，不由后续成功覆盖。旧失败控制器源码 `reports/raw/optimization-resume-extra-failed-controller-68f32db.py` 只作归档证据，不是继续原流程的入口。

第三轮完整报告 `reports/optimization-restart-fallback-68f32db-20261006T195817Z-df658dc1.json` 实际EXIT0，SHA-256 `e3108df183e4cc1793311ed4c22d38480738188eb4bb4d148191795ff0d0f292`；独立控制器 `reports/optimization-final-fallback-controller-68f32db-58fcc66e.json` 记录COMPLETED_FUNCTIONAL_PASS_AND_NORMAL_STOP。执行入口是 `scripts/analysis/run-fallback-final-68f32db.py`，当轮主测试脚本与helper摘要在报告内。相同冻结68核心和server/world身份，三次boot、两次配置切换，正常完成true/true→false/false→true/true。同服不同区块和A→B两个新频道各189 FE实际输入/输出，先提取53、留LOCAL75及共享pool61，重启后OFF实际提取0，开启后提取136，重复提取0；最终pool/owned及本地/WAL余量0，返回fast后仍不能重复提取。checkpoint-only偏斜一次保留，固定期限内完整检查收敛后取得最终连续quiet；观察不修改SQL/WAL，不宣称跨读原子快照、性能结果或外部存档原子性。

`reports/optimization-restart-fallback-after-corrected-audit.json` 确认首轮原128仍为同凭证SQL LOCAL128/WAL镜像128、实际输出0，有效资产128而非256。同存档正常回退的通过不外推运行中热切换或旧二进制混跑。

全新fixture的 `--mode legacy --execute` 也已实际EXIT0：`reports/optimization-final-regressions-legacy-68f32db.json` passed、结束20:03:18Z、无stop_failure，两个子报告摘要与父引用一致。`reports/three-68f32db-legacy.json` 七项检查通过，76000 FE、144 item、6000 fluid仍是最终正RX观察，未全部外部排空；末STATUS中A/B/C累计errors=0/1/2、db_deadlock_retries=1/1/0保留。`reports/optimization-topology-final-legacy-68f32db-20261006T200139Z-541bf9.json` 五case通过，窗口新增错误/拒绝/隔离/死锁重试均0，之前累计值未清除。legacy父SHA-256为 `2849faee1291dce9e8d2a217b905c6bc4330803fa38e20e7dcad6a1fb346f997`，三服/拓扑子SHA分别为 `450420d46e04c8db6f31901145f0d166fba0ee564fec506f96c436b7b96659c3` / `a8015cc4353d93b5efb76741707e0639a51adcaf335c15e052a75e7f0e41df82`。这些是false/false下独立新fixture功能回归，不是计时性能或legacy五halt/Redis/MySQL故障复测。

最后的规模复测发现了真实死锁和异常覆盖问题，已在 `75392af` 修复并实际执行相同完整build/原生命令。该修订为65个JUnit（失败/错误/跳过均0）及13个基础原生测试通过；XML `reports/optimization-tests-savepoint/`，日志 `logs/optimization-build-savepoint.log`，JAR摘要清单 `reports/optimization-artifact-savepoint.json`。新增回归在真实MySQL制造savepoint内的1213死锁，验证1305清理错误作为suppressed保留、有限重试且两份checkpoint变更各提交一次；本地缓冲测试验证OFF的干净pending不产生发送工作而资产/WAL/原业务ID完整保留。后续兼容矩阵和新规模结果另列，不将旧e405失败规模算成通过。

本节针对 `perf/channel-coordinator`；下方客户端及 AE 三服代理报告属于上一轮 `87bf217`，不能当成本轮已重跑结果。首轮性能计时核心固定为 `4cfff0a`。后续只追加关闭/克隆生命周期修复的 `e4057a5` 实际执行 `scripts/gradle-dev.sh build -Dct.integration=true runGameTestServer -PgameTestBackend createServerALaunchScript createServerBLaunchScript createServerCLaunchScript createServerPerfLaunchScript`，63 个单位/性质/真实后端测试与 13 个基础原生测试全部通过、无跳过；XML 在 `reports/optimization-tests-seal-final/`，日志在 `logs/optimization-build-seal-final.log`。`4cfff0a` 的 63+10 结果另存于 `reports/optimization-tests-final-revision/`、`logs/optimization-build-unhydrated.log`。首轮三个失败、一次新增测试的编译错误及原生矩阵失败日志均保留，未用成功结果覆盖失败证据。

`ChannelBatchIntegrationTest` 验证真正共用 Connection 的事务数、逐业务 ID 重试、重复已提交请求的确认丢失语义、局部端点失败、权限/端点版本/会话校验、混合接收公平、满凭证候选跳过、JOIN 载荷校验和 SQL/WAL 恢复门；不是实际切断 COMMIT ACK。profile/quantum 不兼容候选属于 `AuthorityIntegrationTest`，批次套件未单独制造错误 generation/binding 请求。`LocalDeltaTest` 以种子 `2026100601` 运行 64 组真实 LocalBuffer/LocalJournal 随机交错输入与领取；`RuntimeDeltaGameTests` 在真实 Minecraft worker 的发送 WAL 后暂停，同时进行主线程旧 RX 提取和新 TX 输入，再检查三个独立 SQL/WAL 业务凭证及 remaining，不用旧完整快照覆盖结果。完成邮箱测试检查预留容量、并发交付、终态只提交一次及释放；协调器测试检查 single-flight、执行中唤醒、公平轮转和移除。

历史55d87e9拓扑脚本在三独立 JVM 上实际通过：

```bash
python3 scripts/optimization-topology-test.py --label durable-final
```

报告文件名为 `reports/optimization-topology-durable-final-*.json`，覆盖同服相距 64 格的不同区块、同实例 overworld/nether、三服三发送/三接收、RECEIVE→OFF→RECEIVE、空设备拆除后同坐标的新 owner/new ID。每种拓扑使用独立频道，真实能力接受/提取及静止 SQL 所有权核对，保留 RCON 原始应答与 SQL 行。早期 `optimization-topology-verify-20261006T102846Z-fe8f39.json` 虽然业务断言通过，却有注册冲突重复重试；它不是有效性能验收结果。修复后的 `optimization-topology-final-20261006T104322Z-38f5c7.json` 五场景均无新增 worker error、拒绝或隔离。不是在线玩家、任意第三方管道或正余额拆除后人工回收的完整测试。

`three-server-test.py`、`fault-test.py`、`recovery-test.py`、`mysql-outage-test.py` 已在隔离开发后端实际运行，该轮 `55d87e9` 结果分别保存 `three-server-55d87e9.json`、`faults-55d87e9.json`、`recovery-55d87e9.json`、`mysql-outage-55d87e9.json`；上一轮副本另加 `-87bf217-historical` 后缀。该55版故障脚本额外覆盖 `after_local_sql`，共五次实际 `halt(97)`。目标 WAL 对 RESERVED 凭证不构成可领取授权，恢复到隔离端点时不进可用 RX；LOCAL 凭证仍受端点隔离门控制。SQL 和 WAL 相同 allocation 不相加为两份资产。

Redis 实际停机/重启/FLUSHDB 保留 SQL 配额；MySQL 实际停机期间撤销本模组票据、拒绝新增，该轮管理请求实际耗时见 `reports/mysql-outage-55d87e9.json`，恢复后旧持久占用仍为一个。报告中的预期故障错误、配额拒绝和死锁重试保留，不能将这些测试称为“零错误运行”。`4cfff0a` 八种兼容矩阵全部通过，共 108 个原生必需测试，逐组合 10/12/13/15/12/14/15/17 项；日志 `logs/optimization-compat-unhydrated-final.log`，逐组合状态见 `compat-matrix-4cfff0a.json`。AE 旧测试驱动在加速 GameTest tick 中无界重复观察库存而填满有界 worker 队列，已改为一个在途观察；资产断言和队列上限不变，详细原因见 `logs/optimization-ae-diagnosis.log`。

最后追加的 `RegistrationRecoveryGameTests` 真实创建并领取一个 128 FE SQL/WAL 凭证，在恢复 WAL fsync 后暂停实际 worker；主线程卸载设备，显式注入 SQLState 08006 确认失败，然后验证 closing 结束、原 WAL 和独占凭证保留、没有默认空检查点及错误隔离。重新加载使用同一凭证，实际能力提取 128 一次、再次零，并核对 SQL CONSUMED。此项是明确故障注入，不是真正停止 MySQL；真正容器停机由独立 `mysql-outage-test.py` 覆盖。五个 halt 与三服/Redis/配额报告的 `55d87e9` 副本保留，最后的未注册卸载门由 `4cfff0a` 原生全组合回归验证，不混称每份报告都来自同一提交。

`e4057a5` 另有三个真实后端原生测试：未恢复但实际已提交注册的设备被物理拆除，SQL 确认和封存各失败一次后仍保留 closing 重试、原 128 FE WAL 与独占资产，最终 SEALED；注册 SQL 前失败且明确没有 WAL/端点与 SQL 已提交但确认失败分别处理，不以失败应答推断无资产；克隆 NBT 中相同设备 ID 的新方块被拆除，不改原设备的票据、SQL 所有权或本地调度，原 128 FE 只可提取一次。这些 worker 钩子注入 SQL 异常，不能冒称真实数据库断网。e405该轮八种组合为 13/15/16/18/15/17/18/20，共 132 项必需原生测试，全部通过；报告 `reports/compat-matrix-e4057a5.json`，日志 `logs/optimization-matrix-e4057a5/`、`logs/optimization-compat-seal-final.log`。

未逐项执行：真实在线专用服 GUI、新旧路径运行中热切换、1000 端点多 JVM 物品组件热点、广泛第三方异常副作用、磁盘设备级错误、8192 closing 准入溢出的原生容量注入、延迟网络下热振荡和长期历史增长。配置切换只支持正常停机后重启。性能前后条件、观察误差及每项验收结果见 [本轮基准方法](OPTIMIZATION_BENCHMARK.md)。

测试只连接脚本建立的本机 `cross_tesseract` 开发数据库和 Redis。执行前接受 EULA，阅读各故障脚本说明。结果以 `reports/*.json`、完整 `logs/` 和 JUnit XML 为依据；测试规模不等于容量承诺。

```bash
scripts/install-jdk.sh
scripts/fetch-references.sh --with-gt-runtime
scripts/dev-backends.sh
python3 scripts/setup-dev.py --accept-eula
scripts/gradle-dev.sh test -Dct.integration=true
# 首次 GT 原生测试先按 COMPATIBILITY.md 构建完整 GT/MUI runtime。
scripts/test-matrix.sh
```

普通 `test` 会跳过需要后端的测试；本次验收实际使用 `-Dct.integration=true`，没有用 H2 替代 MySQL，也没有以内存 Redis 计算资产。单位及性质测试覆盖缓冲模拟/执行、部分领取、重复凭证、Long 溢出、200/300 次随机热/资源性质检查、载荷与 WAL 损坏、AE 代理规划。真实后端覆盖邀请并发接受、唯一主人、配额竞争、幂等余额、超过 2^53 的整数、SQL 死锁重试、outbox 未发布提交、Redis pending/消费者重启/重复和乱序、并发迁移及中断 DDL、隔离凭证恢复和历史容量。

`test-matrix.sh` 顺序启动八个真实 NeoForge GameTest JVM：基础、Mek、AE、Mek+AE、GT、GT+Mek、GT+AE、三兼容同时存在。每次都有真实 MySQL/Redis，模组缺失组合不解析对应运行类。GT 是指定 FortyTwoCn 源码构建，缺失 ModularUI preview 使用明确记录的 3.3.1 替代闭包；见 [兼容版本](COMPATIBILITY.md)。脚本读取原生 GameTest 成功数和 Gradle 退出状态写报告，失败不算通过。

原生游戏测试覆盖完整 ItemStack/FluidStack 组件、无效注册表/超大嵌套载荷拒绝、方向与 simulate、真实 vanilla chest 多槽部分接收、能力缓存失效、GT 实际能量仓与电压/安培、Mek 化学品 long/剩余量/放射性拒绝及热量、AE 真实 MEStorage 和 managed nodes 的频道不足/恢复。它们没有证明所有第三方管道、可移动机器和外部存储引用都兼容。

库存补齐时的历史单元/真实后端测试共 27 个，新增指定资源需求、幂等重复、独占预留与取消不退款、无权限资源元数据拒绝、8+2 行分页、八请求上限、期限与绑定切换。AE 原生测试增加真实模拟零副作用、本地短缺立即返回、持久请求及完整组件指定到货。命令 `scripts/gradle-dev.sh test -Dct.integration=true runGameTestServer -PgameTestBackend -PtestMods=ae2`；日志 `logs/stock-ae-tests.log`。

## 三个独立服务器

按 README 建立并启动 A/B/C 后：

```bash
python3 scripts/three-server-test.py
python3 scripts/mysql-outage-test.py
python3 scripts/recovery-test.py
python3 scripts/fault-test.py
```

三服测试通过控制台隔离 fixture 行为调用真实服务端能力与数据库：A 建频道、B 邀请、C 接受；A→B/C 物品/流体/FE 守恒，A/B→C 多发送；三服同时申请同一玩家配额最终恰好两个；同区块两设备关闭其一不影响另一票据；成员自己的配额与移除后的有界撤权。控制台 fixture 的 UUID 不是在线玩家认证测试，本项目没有将它冒称为真实代理转发联调。

MySQL 故障实际停止容器并重启，验证票据撤销、持久名额保留、新批准拒绝以及 Minecraft 命令响应。Redis 故障实际停止服务、重启并 FLUSHDB，仅影响可恢复提示，不删除 SQL 资产。恢复测试正常停止/重启真实 Minecraft，再 SIGKILL；故障注入在五个 WAL/SQL 阶段 `halt(97)`，确认新 epoch 隔离、不超时退款、不重复再发。运行这些脚本期间不要并行操作同一测试服务器或后端故障。

## AE 两层分别验证

Level 1 的原生存储测试位于 AE GameTest；Level 2 本地真实节点/规划器测试单独执行，不能合称“原生网络已合并”。三服实验代理测试使用：

```bash
scripts/gradle-dev.sh createServerALaunchScript -PtestMods=ae2,mekanism -PaePrototype
scripts/gradle-dev.sh createServerBLaunchScript -PtestMods=ae2 -PaePrototype
scripts/gradle-dev.sh createServerCLaunchScript -PtestMods=ae2,gregtech -PaePrototype
# 分别在三个终端启动 A/B/C，再执行：
python3 scripts/ae-three-test.py
```

该测试查询真实 grid UUID/频道消费者；B/C 原生缺货立即返回零并记录两份持久需求，然后跨 JVM 插入/提取二十四个钻石，并检查同网多桥、失电及撤权。报告 `ae-three.json` 仅证明报告中列出的实验语义；控制器/安全/电力/合成服务的原生合并尚未完成。

## 客户端与独立安装包

实际 Xvfb 客户端打开本模组 GUI，通过 Minecraft C2S 包创建/绑定频道及设置 FE，保存英文和小窗口中文截图，见 `reports/screenshots/`、`logs/stock-ui-smoke.log`。复现：安装 Xvfb 后运行 `scripts/ui-smoke-headless.sh`，它分配独立显示会话并正常清理；也可自行设置 DISPLAY 后运行 `scripts/gradle-dev.sh runClientSmoke`。测试使用真实 integrated ServerPlayer；真实在线专用服 GUI、所有管理页操作和全部窗口尺寸仍未逐项实测。

安装真实 AE 的库存 GUI 扩展测试使用 `scripts/ui-smoke-headless.sh -PtestMods=ae2`：原生 AE 实际插入 32 钻石，SEND 模式显示远端 32/本地 0；RECEIVE 到货显示本地 32，C2S 调货 1 个形成未分配需求，C2S 取消后本地 32 保持。扩展通过以 `CT_UI_STOCK_PASS`、Gradle 成功和 `reports/stock-ui.json` 为准，截图分别记录远端观测及待分配状态。

重复测试使用新空坐标，保留上轮世界/封存资源。开发过程中 `stock-ui-registration-failed.log`、`stock-ui-sealed-location-debug.log` 保留旧固定位置受封存阻止的失败；`stock-ui-assisted-debug.log` 为有人工点击诊断的一轮，不能算无人干预通过。`stock-ui-teleport-debug.log`、`stock-ui-ground-height-debug.log`、`stock-ui-heightmap-debug.log` 保存空坐标布置/未加载高度图的测试失败；已按实际 1.21.1 Level/Chunk 源码预生成测试区块后读取高度，等待客户端位置/区块确认，并限制总测试时长及重生次数。最终库存测试只有 `stock-ui-smoke.log` 且两种 PASS 标记/正常退出同时存在才计为通过。界面绑定在服务器确认 registered 前停用。截图复核发现第一轮远端截图抓取早于渲染，保留为 `stock-ui-pre-render-delay.log` / `ui-stock-zh-remote-pre-render-delay.png`；最终开发 hook 等待八个客户端 tick 渲染后再抓取，避免将上一帧加载状态作为库存证据。

独立包测试使用官方 NeoForge installer 的冷安装目录，直接 `run.sh --nogui` 加载最终 Jar-in-Jar 产物，不依赖 Gradle 开发 classpath。独立安装报告及构建清单另保存在 `reports/`。

历史 `75392af` 冷包只装本模组，真实 MySQL/Redis 下 1234 FE 能力接受/提取及正常停止通过。JAR SHA-256 `fc7a072581630ed39125d6bf00d362df5e51200f6dabc40c85a47d98b16975e8`，报告 `packaged-smoke-75392af.json`、日志 `logs/packaged-smoke-75392af.log`。753该轮八组合为13/15/16/18/15/17/18/20，共132项全部通过，报告 `compat-matrix-75392af.json`、日志 `logs/optimization-matrix-75392af/`。历史 `e4057a5` 冷包摘要 `77bc944a6c2bbe11dcc7d4a811163821d2502e8bb81926feccda0bed96d0769a` 与 `4cfff0a` 摘要 `4cd0d4b7be1a30946ebfbb72cc554962ce7655d8bb8218797d8a0d07e95a2859` 的独立报告另保留，不声称旧计时使用了当前 JAR。这是已有隔离安装目录中的新坐标测试，包含旧测试设备，不当作空世界性能测试。

```bash
scripts/gradle-dev.sh build -Dct.integration=true
scripts/install-packaged-dev.sh --accept-eula
python3 scripts/packaged-smoke.py
```

## 未验证边界

任意外部容器保存回退不具原子保证；生产 TLS/可信代理认证、所有大型 modpack、网络高延迟/丢包、1000 端点多 JVM 热点物品组件及完整 AE crafting 恢复未验证。性能脚本与指标含义见 [性能报告](PERFORMANCE.md)。不要把短测试外推为长期生产完整性或吞吐承诺。

`9258a6a` 八组合实际全部通过，13/15/16/18/15/17/18/20，共132项，报告 `compat-matrix-9258a6a.json` 与 `logs/optimization-matrix-9258a6a/`。官方冷包最终JAR也完成1234 FE输入/输出并退出0，报告 `packaged-smoke-9258a6a.json`。首次冷包在spawn时碰到旧时间取模坐标的location_sealed，实际未输入资源；失败日志/报告 `packaged-smoke-9258a6a-first-failed.*` 保留。烟雾驱动改用新UUID坐标后独立重跑，不删除封存记录、不接受新EULA。
