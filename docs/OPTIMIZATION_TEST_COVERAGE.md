# 本轮32类正确性与故障覆盖

当前测试基线为 `68f32db439f445b8f72faf92dc62fbc5b9dce738`；下表首次逐项审计基准 `9258a6ade8c94e863a450a3f5eec95dff9c9ee2b` 的证据版本继续保留。本页只核对已保存的源码、XML和报告，没有执行新测试或访问计时现场。下表按用户32项原编号映射，记录具体已执行部分与缺口，不将一个场景的局部断言当作该场景全部组合通过。9258的规模数据不归入68版。

当前68版追加证据：

- **U/R，68**：[68项XML](../reports/optimization-tests-ready-final/xml/) 实读失败/错误/跳过全部为0，35项单元/性质与33项真实后端（Authority 19、ChannelBatch 13、Migration 1）。新增query测试与既有partial-batch/随机pending模型断言核对poll后的首次在途唤醒、移除/重绑定和旧完成不丢新信号；没有新缓存字段或资产授权。构建版本与命令见 [68版清单](../reports/optimization-artifact-ready-final.json)。
- **G，68**：13项基础原生GameTest与 [八组合矩阵](../reports/compat-matrix-68f32db.json) 全部通过；仍为13/15/16/18/15/17/18/20，共132次执行，不是132个独立场景。
- **P，68**：[官方冷包](../reports/packaged-smoke-68f32db.json) 实际输入/提取1234 FE并退出0，源码与模组JAR摘要按68版构建清单核对，不以9258冷包替代。
- **已结束观测，68**：[规模六窗](../reports/optimization-scale-comparison-68f32db.md)、[真实箱子六次探测](../reports/optimization-container-comparison-68f32db.md)、[背压/热点六窗](../reports/optimization-pressure-comparison-68f32db.md) 均有独立当前版本报告。压力包含冷频道低流量负载，但独立E2E探测为0；记录有限窗口中所有接收端及冷频道实际服务，不能补成长时间无饥饿或实际TPS证明。规模的Runtime滚动p95相对原版仍有回归，原版完整窗DB起点缺失继续保留。
- **三服FE主比较**：[原版87/仅合批68/快速68的27个样本](../reports/optimization-comparison-68f32db.md) 全部功能完整，覆盖同服、纯跨服与混合路径各三重复，混合每轮两接收端均有实际输出。严格性能比较实际退出1：仅合批未达同服40%延迟目标，快速模式三路径均未达30%事务目标。原版raw HEAD=753是当时checkout，完成序列SHA绑定的运行版本声明为87；此声明不是classloader attestation。
- **同频道资源smoke，68**：[组件物品/FE/水](../reports/optimization-resource-mix-smoke68-20261006T185222Z-877b8b.json) 实际通过，配置仅1秒、一次重复，补充第15/16项的组件与资产核对，不算正式性能稳态。
- **正式同频道混合，87/B68/C68**：[原版](../reports/optimization-resource-mix-original87-20261006T185321Z-8c23fc.json)、[仅合批](../reports/optimization-resource-mix-batch68-20261006T190206Z-258fe6.json)、[快速](../reports/optimization-resource-mix-fast68-20261006T191056Z-43958a.json) 各三次真实30秒预热/120秒观察，九窗均passed，子文件SHA与 [extra序列](../reports/optimization-extra-sequence-68f32db.json) 引用一致。每窗不同CUSTOM_NAME的stone各32个经实际源/目的箱，同频道FE与水分别核对能力接受/提取与最终SQL/本地零余量；补充第7/15/16项，未扩大到所有兼容资源或最大组件。功能通过不消除性能回归：B两种组件输入→外箱完整接受上界的三重复中位数71.097889/78.184268秒，原版29.287011/30.355341秒。父extra序列因后续回退失败仍为FAILED，不改成整体成功，详情见 [PERFORMANCE.md](PERFORMANCE.md)。

## 68 fast 实际回归补充

以下五份独立阶段报告已结束，归属68核心、`channelBatches=true/localFastPath=true`；不能外推仅合批或关闭两开关的完整回退结果。运行版本声明与源码/启动归档绑定，不等于独立classloader attestation。三服资源/配额、拓扑、五halt、恢复/Redis与MySQL停启实测如下；父回归流程在随后回退失败，不能把这些完成阶段称为整套通过。

| 用户编号 | 当前实际证据 | 结论与仍未覆盖的边界 |
| --- | --- | --- |
| 1、2 | [五项拓扑](../reports/optimization-topology-final-fast-68f32db-20261006T192008Z-6be3bb.json)：同服相距64格的4096 FE、overworld→nether的3072 FE均实际接受/提取并核对静止SQL | 五case均passed；三个JVM观察窗口新增worker错误/拒绝/隔离/死锁重试均0，早先累计计数没有删除。仅FE，未外推任意资源/机器或在途强制卸载 |
| 3、10、14、15 | [三服资源/配额](../reports/three-68f32db-fast.json)：邀请接受、多资源守恒、A/B多发送、同区块独立票据、三JVM竞争恰好两个ACTIVE、移成员后能力关闭 | 套件exit0；接收缓冲观察合计76000 FE、144 item、6000 fluid，两收端均获资源且BOTH的旧RX不回流。该报告保留正RX，不冒称全部外部提取后的零余量；控制台UUID不是在线玩家认证 |
| 4、5 | 同份拓扑 `mixed_endpoints`：ABC三发送/三接收，9轮×3源×128 FE，总3456 FE；三个收端实际提取896/1280/1280，保存global last_grant | 所有收端在有限窗获服务，不要求均分；不能证明无限时间无饥饿 |
| 9、10 | 同份拓扑 `mode_resume` 与 `replacement`：RECEIVE→OFF→RECEIVE；旧321 FE实际提取后空设备拆除退休，同坐标新ID未继承transfer/grant/旧频道成员关系，再独立提取97 FE | OFF期间旧登记/在途allocation仍可保持独占，未按模式关闭退款。正余额拆除人工回收和任意传输/热任务卸载交错仍未由此实测 |
| 12、14、29 | [恢复/Redis](../reports/recovery-68f32db-fast.json)：正常重启恢复授权ticking票据；实际停止Redis撤票但保留配额；重启/FLUSHDB不删权威配额；硬kill后新epoch隔离且不恢复旧票据 | 当前实际Minecraft进程/Redis故障已测；不是网络延迟/丢包矩阵，也不能从硬kill票据fixture推导任意已开放RX/外部存档回退守恒 |
| 14、30 | [MySQL实际停启](../reports/mysql-68f32db-fast.json)：该次测试耗时7.918233秒，故障时实际票据0/持久槽1/新批准0，恢复实际票据1；管理RCON应答0.980320ms | 故障快照errors=1、末尾累计errors=2保留，不称零错误；应答为database_unavailable，不是故障时成功授予。单次响应不证明所有超时/COMMIT模糊结果或长期断网边界 |
| 23、24、25、26 | [五次真实halt](../reports/faults-68f32db-fast.json)：after_send_wal、after_deposit、after_allocation、after_receive_wal、after_local_sql，均实际halt(97)后验证新epoch隔离、所有权保留、不按超时退款 | 补齐当前fast的这五个WAL/SQL边界；after_deposit是提交后进程中断，不是切断COMMIT应答网络。未强制多端点/多publication分组的部分组提交后halt，外部容器仍是另一事务域 |

三服脚本有两次预期配额拒绝。其C末尾累计快照明确为 `errors=2`、`db_deadlock_retries=2`，不能把本次回归概括为零错误、零锁争用；拓扑使用之后的独立baseline/delta，新增计数为0与该累计快照不矛盾。

第20项当前回退的前两轮失败证据保留。首轮在fast_prepare_positive_assets由验证器strip丢弃FE空HEX列而失败，尚未配置切换；[首轮只读审计](../reports/optimization-restart-fallback-first-failure-audit.json) 确认唯一实际128 FE输入、0输出，SQL LOCAL128与同凭证WAL镜像128，有效资产是128而非256。失败父序列及该fixture保留，未重放原输入/输出。

[第二轮回退](../reports/optimization-restart-fallback-68f32db-20261006T194856Z-b6a7c332.json) 已完成同世界正常true→false重启，新same/cross各189 FE实际输入与输出、重复提取0，但SQL先读checkpoint8而WAL随后10的跨时刻观察使quiet验证失败；[续跑父报告](../reports/optimization-resume-extra-68f32db-20261006T194822Z-c221422a.json) 同样EXIT1。[新两频道只读审计](../reports/optimization-restart-fallback-second-failure-assets-audit.json) 确认378 FE实际输出、SQL/WAL有效剩余0；[原fixture再次审计](../reports/optimization-restart-fallback-after-second-failure-audit.json) 确认原128仍有效128、实际输出0。两个失败及extra父FAILED不改成PASS。

[第三轮完整回退](../reports/optimization-restart-fallback-68f32db-20261006T195817Z-df658dc1.json) 已实际EXIT0，SHA-256为 `e3108df183e4cc1793311ed4c22d38480738188eb4bb4d148191795ff0d0f292`；[独立控制器](../reports/optimization-final-fallback-controller-68f32db-58fcc66e.json) 确认COMPLETE功能通过及正常停服。同一冻结68核心、server/world身份，经三次boot和两次配置切换，完成true/true→false/false→true/true。两个新频道为同服不同区块和A→B，各189 FE实际输入、189实际输出、SQL pool/owned余量0，重复提取0；重启前已部分提取53、保留LOCAL75与共享pool61，恢复时OFF接收端实际提取0。一次checkpoint-only偏斜保留原始观察，在固定期限内重新满足完整检查并取得最终连续quiet，不修改SQL/WAL、不把采样读称为原子快照。[第三轮后原fixture审计](../reports/optimization-restart-fallback-after-corrected-audit.json) 仍为原凭证LOCAL128/WAL镜像128、实际输出0，有效资产128。此回退不证明热切换、旧二进制混跑或外部世界回档原子性。

**当前68 legacy新fixture补充**：[关闭两开关的完整父报告](../reports/optimization-final-regressions-legacy-68f32db.json) 已实际EXIT0、passed、结束时间20:03:18Z且无stop_failure，独立SHA引用的 [三服](../reports/three-68f32db-legacy.json) 七项检查与 [拓扑](../reports/optimization-topology-final-legacy-68f32db-20261006T200139Z-541bf9.json) 五case均通过。补充第1–5/10/14/15项在false/false配置下的新fixture，不以fast结果替代。三服总76000 FE、144 item、6000 fluid仍是最终正RX观察，未全部外部排空；末STATUS的A/B/C累计errors为0/1/2、db_deadlock_retries为1/1/0，均保留。拓扑窗口三服新增错误/拒绝/隔离/死锁重试均0，但没有清除这些先前累计值。该套件没有重跑legacy五halt/Redis/MySQL故障，也不是性能或世界保存原子性证明。原9258初审表继续保留如下。

9258初审证据（保持原版本）：

- **U/R，9258**：[67项XML](../reports/optimization-tests-hotspot-final/xml/) 全部失败/错误/跳过为0。其中34项为单元/性质测试，33项为真实后端测试：Authority 19、ChannelBatch 13、Migration 1。后三类使用真实MySQL，部分也使用真实Redis；三个Authority对象不是三个Minecraft JVM。构建版本、命令和产物见 [清单](../reports/optimization-artifact-hotspot-final.json)。
- **G，9258**：构建的13项基础原生GameTest通过；[八组合矩阵](../reports/compat-matrix-9258a6a.json) 为13/15/16/18/15/17/18/20，共132次必需测试执行，全部通过。基础测试在组合间重复，132不是132个独立测试场景。可选组合启动真实NeoForge与实际AE/Mek/GT接口。
- **P，9258**：[官方冷包](../reports/packaged-smoke-9258a6a.json) 实际输入/提取1234 FE并退出0，模组JAR SHA-256为 `f0c7a9b344af7ca7a4d635ca61e5c7565046de441400635b67123754854b01f1`，与构建清单一致。首次 `location_sealed` 失败另存，不计为通过。
- **H，55历史**：[拓扑](../reports/optimization-topology-durable-final-20261006T111122Z-868e0d.json) 自带 `git_head=55d87e9…`；[三服](../reports/three-server-55d87e9.json)、[五次halt](../reports/faults-55d87e9.json)、[恢复/Redis](../reports/recovery-55d87e9.json)、[MySQL停机](../reports/mysql-outage-55d87e9.json) 按独立历史版本归档。它们证明该轮实际执行的边界，不能替代9258复测。
- **9258初审时未归档**：9258对应三服资源/配额、五次halt、Redis/MySQL实际停机恢复及同一JAR关闭新开关后的回退当时未执行归档。已有4cfff0a/75392af性能结果也不改写为9258结果；68版追加证据见上文。

下表保留9258初审事实；源码链接指当前仓库的同名测试便于定位，执行版本由对应XML/报告确定，不能以当前行号证明历史源码。H项另由历史报告确定版本。U是实际执行的单元/性质测试，R是真实后端集成测试，G是真实Minecraft原生测试，H是历史版本实测。源码有保护分支本身不算故障实测。

| # | 用户场景 | 已执行证据、类型与版本 | 9258初审覆盖边界；68补充见上文 |
| --- | --- | --- | --- |
| 1 | A1→A2同服不同区块 | H55拓扑 `different_chunks`：相距64格，实际FE接受/提取4096，静止SQL核对 | 历史实测；9258同拓扑待复测，未扩展到所有资源/工厂容器 |
| 2 | 同实例跨维度 | H55 `cross_dimension`：overworld→nether，实际FE 3072 | 历史实测；9258待复测，不外推卸载维度或任意第三方机器 |
| 3 | 纯跨服 | H55三Minecraft JVM：FE 76000、item 144、fluid 6000；R9258 [整数守恒](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L95) | 当前后端守恒已测；9258真实三服待测，三个Authority不是三游戏服 |
| 4 | 混合同服与跨服 | H55 `mixed_endpoints`；R9258 [远端先登记需求优先](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L127)，核对global last_grant及守恒 | 当前SQL公平已测；历史三服短窗不是长期无饥饿证明，9258三服待测 |
| 5 | ABC多发送/多接收同频道 | H55三源/三收、27次输入，FE 3456，各收端896/1024/1536；R9258 [多设备一次事务](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L71) | 当前单Connection合批已测；实际9258 ABC多发多收待测，不要求均分 |
| 6 | 热点与低流量多频道竞争 | U9258 [热点回尾](../src/test/java/dev/crosstesseract/ChannelCoordinatorTest.java#L65)、[性质状态模型](../src/test/java/dev/crosstesseract/ChannelCoordinatorTest.java#L229)；753历史1000端点最多四频道规模记录 | 协调器轮转已测；未完成真实多JVM热点/低流量异质频道长期竞争，也无最大载荷下统一堆准入验证 |
| 7 | SEND/RECEIVE/BOTH与外部管道 | G9258 [vanilla chest自动收发](../src/main/java/dev/crosstesseract/test/CoreBackendGameTests.java#L45)、[方向/能力](../src/main/java/dev/crosstesseract/test/CoreBackendGameTests.java#L61)，矩阵包含实际GT能量仓、AE存储、Mek能力 | 当前部分实测；BOTH的RX不回流TX已断言。未穷尽第三方管道、别名库存和可移动机器 |
| 8 | 接收空间动态变化 | U9258 [部分消耗/凭证位](../src/test/java/dev/crosstesseract/LocalRoomTest.java#L11)、[整体prospective admission](../src/test/java/dev/crosstesseract/LocalDeltaTest.java#L141)；G9258胸箱60→64及下一槽20 | 当前已测数量空间、凭证空间和部分输出；未强制覆盖每种资源在phase 2前空间缩减的实际机器交错 |
| 9 | 满载、卸载、拆除重放置 | R9258 [9 ITEM/32 FE满凭证候选含QUAR排除](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L229)；G9258 [卸载恢复](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L65)、[128 FE拆除重试](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L160)、[克隆拆除](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L306)；H55空设备新ID替换 | 当前生命周期部分实测；未原生注入8192 loaded/closing上限，未覆盖一般区块卸载时的所有传输/热在途组合。硬崩溃前SQL未提交的拆除意图仍仅在内存 |
| 10 | 在途换绑定、撤权、移成员、状态改变 | G9258 [异步绑定停输入/旧回复拒绝](../src/main/java/dev/crosstesseract/test/CoreBackendGameTests.java#L19)；R9258 [旧版本/撤权savepoint隔离](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L195)、[publication重新授权](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L339)；H55移成员能力关闭 | 当前新旧权限/版本SQL门已测；未把正余额在途任务与每类成员/频道状态变更全部做原生交错 |
| 11 | 旧权限、通知、回调 | G9258旧PermissionSnapshot不能回滚绑定；R9258 [重复/乱序定向提示](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L164)；U9258 [旧lease完成不抹新signal](../src/test/java/dev/crosstesseract/ChannelCoordinatorTest.java#L114)、重复终态拒绝 | 当前部分已测；没有单一原生用例强制同一旧transfer回调在新BE生命周期、旧权限和旧hint同时到达 |
| 12 | 重启epoch | R9258 [新boot同时fence两个SQL阶段](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L558)；H55实际正常重启与SIGKILL后隔离 | 当前后端epoch已测；9258实际游戏进程硬重启恢复待测 |
| 13 | 重复server.id、旧实例fence | R9258 [duplicate_server_id与clone](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L150)、[过期旧会话](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L308) | 当前真实SQL拒绝/替换fence已测；不是两个同时在线Minecraft以同server.id运行的实测 |
| 14 | 配额合批与故障不变 | R9258 [三Authority争两个槽](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L66)、同区块计两份、安装失败补偿、降额与撤销ACK；G9258克隆不能撤原实际票据；H55三JVM配额/Redis/MySQL停机 | 当前权威政策与部分真实票据已测；9258三JVM并发及实际故障复测待测 |
| 15 | 同资源部分接收、多资源 | U9258 [定量剩余回原credit](../src/test/java/dev/crosstesseract/BufferSafetyTest.java#L11)；G9258 item/fluid/FE/EU/chemical的实际接口及部分领取；H55跨服item/fluid/FE | 当前本地/后端部分接收已测；未将所有资源混合到实际三服单批中 |
| 16 | 同item不同组件 | G9258 [完整组件round trip](../src/main/java/dev/crosstesseract/test/GameTests.java#L32)、[AE指定组件到货](../src/main/java/dev/crosstesseract/compat/ae2/AeGameTests.java#L38)；R9258 [完整payload字节不合并](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L267) | 当前组件与字节身份已测；未做大规模最大组件热点 |
| 17 | 最大载荷、long边界、非法溢出 | G9258 [超限/深层/恶意数组拒绝](../src/main/java/dev/crosstesseract/test/GameTests.java#L20)、Mek >2^53与GT Long.MAX_VALUE输入；R9258 [单端点long溢出隔离](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L303)，整数守恒 | 当前超限拒绝及受检整数已测；合法近64KiB组件端到端成功边界、1000种最大组件堆占用未测。不是所有long运算的穷举 |
| 18 | simulate无副作用 | U9258 200次部分领取性质；G9258方向/物品/流体、AE模拟不产生持久需求、Mek调用者不变且模拟不入账 | 当前受支持接口已测；不承诺异常第三方自身的simulate纯度 |
| 19 | 旧快照并发不回滚remaining | U9258 [旧delta+新输入/消费](../src/test/java/dev/crosstesseract/LocalDeltaTest.java#L39)、固定seed `2026100601` 的64组交错；G9258 [真实worker WAL hold](../src/main/java/dev/crosstesseract/test/RuntimeDeltaGameTests.java#L26)：旧RX128消费23，新TX64+7，最终RX176/TX0，SQL三个业务凭证及remaining105 | 当前真实主线程/worker并发及WAL已测；该原生用例是FE，不是所有外部机器/热状态交错 |
| 20 | 新旧路径切换、重复回调/请求 | U9258完成Reservation终态只提交一次、重复credit不复活；R9258 [重复business ID与publication](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L163) | 当前幂等已测；9258同JAR干净重启关闭两个开关的实际回退待测。配置只在启动读取，运行中热切换不支持，旧二进制混跑未验证 |
| 21 | 批内单端点失败 | R9258旧版本/撤权、long溢出与新Resource回滚、[坏outstanding payload隔离](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L435)，健康端点提交；publication拒绝保持RESERVED无退款 | 当前真正SQL事务/savepoint隔离已测；不是原生任意LinkageError、断盘与每种资源失败的全部排列 |
| 22 | 完成、后台、资源队列满 | U9258 [满容量含待worker及已排队](../src/test/java/dev/crosstesseract/CompletionMailboxTest.java#L16)、8线程争3位、64个已接纳callback完整交付、重复终态/回调异常释放；协调器ready/flight总界、零额占全局64、满凭证SQL候选；R9258 [历史容量原子拒绝](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L248) | 当前helper并发/资源容量已测；未在真实Minecraft Runtime强迫完成邮箱满、worker拒绝并同时核对持久资产/inFlight终态，也未逐项强迫hint队列/序列化预算/批次字节上限耗尽。旧AE观察驱动填满worker队列是失败诊断，不是新协议通过用例 |
| 23 | 发送WAL后deposit前崩溃 | H55 `after_send_wal` 真实halt(97)，新epoch隔离、所有权保留、不退款；G9258 RuntimeDelta在同点hold后正常release | 当前hold并发已测；真实9258 halt恢复待测，hold不是崩溃 |
| 24 | SQL已提交、ACK丢失 | R9258重发已经提交的原business IDs，验证不重复；G9258 [after_register_sql确认异常](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L239)、[恢复WAL后checkpoint确认失败](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L65)；H55 `after_deposit` 提交后halt | 当前实际SQL加显式确认失败注入已测；并未切断COMMIT应答网络。Faults日志明确 `actual_database_outage=false`；after_restore_wal异常在checkpoint之前，不能称该checkpoint已COMMIT |
| 25 | allocation后目标WAL前崩溃 | H55 `after_allocation` 真实halt(97)，独占RESERVED保留 | 历史实测；9258真实halt待测。R9258检查RESERVED不自动可取不替代进程崩溃 |
| 26 | 目标WAL后markLocal/内存前 | H55 `after_receive_wal` 与 `after_local_sql` 两次真实halt；R9258 [撤权拒绝RESERVED恢复](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L492)、[fresh fenced恢复先LOCAL](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L529) | 当前SQL/WAL恢复门已测；9258真实两处halt待测，不把目的WAL当领取授权 |
| 27 | 内存应用重复或重启 | U9258重复credit、消耗后的zero tombstone不复活；R9258 [zero WAL/旧正SQL恢复到CONSUMED](../src/test/java/dev/crosstesseract/ChannelBatchIntegrationTest.java#L374)；G9258同credit恢复只提128一次 | 当前零额/重复身份和恢复已测；实际已开放RX后9258 Minecraft硬重启待测，任意外部存档回退不具原子保证 |
| 28 | 批量部分阶段中断 | R9258两阶段各一次事务、单端点savepoint回滚及publication逐端点授权拒绝；H55五个提交边界halt | 当前事务阶段及局部失败已测；未真实halt含多个端点/多个publication分组的批次来证明部分组提交后的全体恢复。55故障fixture不能替代这一多端点情形 |
| 29 | Redis提示丢失、重复、乱序、裁剪、重连 | R9258 [pending旧consumer接管、重复/乱序、定向ACK、trim](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L164)、[未发布outbox](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L142)；H55实际停止/重启/FLUSHDB后配额保留 | 当前真实Redis/SQL提示幂等已测；9258Minecraft实际断Redis重连待测，未注入网络高延迟/丢包 |
| 30 | MySQL超时、断连、死锁恢复 | R9258 [真实1213死锁](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L265)、[savepoint清理1305受抑制且有限重试](../src/test/java/dev/crosstesseract/AuthorityIntegrationTest.java#L275)；G9258 checked SQLException恢复/封存注入；H55实际停MySQL撤票、保留名额、恢复 | 当前真实死锁/确认异常已测；9258实际停库/恢复待测。注入异常不是真实停库；没有覆盖每个网络超时/COMMIT模糊结果，无所有死锁消失保证 |
| 31 | WAL写失败、磁盘与checkpoint异常 | U9258 [校验损坏/旧版本](../src/test/java/dev/crosstesseract/JournalAndHeatTest.java#L17)、[同revision不同内容拒绝](../src/test/java/dev/crosstesseract/LocalDeltaTest.java#L114)；G9258 [NBT领先WAL停止恢复重试且保留128](../src/main/java/dev/crosstesseract/test/RegistrationRecoveryGameTests.java#L31)；正常WAL写使用真实文件fsync | 当前逻辑冲突/损坏已测；没有注入ENOSPC、EIO、短写、ATOMIC_MOVE/目录fsync失败、权限错误或设备掉电。不把正常fsync与checksum拒绝称设备级故障通过 |
| 32 | 第三方先副作用再不确定异常 | U9258 definite partial remainder回原credits且不能重复；源码 [NeighborPump隔离](../src/main/java/dev/crosstesseract/block/NeighborPump.java#L29) 与外部IO门；G9258正常vanilla/GT/AE/Mek部分交付 | **不确定副作用故障本身未测**：没有真实或测试能力先扣/增外部资产再抛异常、返回错误剩余量的原生fixture。源码选择隔离且不推断零交付，无法证明外部内容或存档守恒 |

## 不能由上述通过数补齐的边界

完成邮箱单元测试的容量分别为1/2/3/64，验证的是helper协议。Runtime的 [submit](../src/main/java/dev/crosstesseract/runtime/RuntimeService.java#L144) 先预留 `config.queueSize()*2` 容量，再向有界worker提交；拒绝前不启动SQL任务，worker拒绝后经原Reservation交付失败。这个代码接线不能代替运行期满邮箱/满worker的资产回归。`limits.loadedEndpoints` 默认8192的closing溢出同样只有代码边界，尚无原生满容量注入；拒绝保持unclean与WAL/SQL原状，代表未知状态待管理员审查，不能算SEALED成功。

热力的当前U/R/G覆盖无NaN/Infinity、容量检查、局部交换不越过平衡、prepared独占与残差/pending持久化、实际Mek热能力与SQL/WAL提交。300次局部热性质测试和一次原生被动交换不证明网络延迟、乱序、多端点反馈环下没有振荡；延迟热网络与封存热资产自动回收未完成。本轮普通资源热点修复没有改变热协议。

性能报告的 `tick_ms_*` 是模组Runtime滚动分布；`mc_recorded_tick_ms_avg100` 是Minecraft内部记录平均值，`mc_target_ticks_per_second` 是目标值。它们不是完整wall MSPT分布或实测实际TPS。已归档并解析的87bf217/75392af/9258a6a/68f32db JFR支持各自冻结来源的采样热点、顶层GC暂停与分配样本权重；[68摘要](../reports/optimization-jfr-68f32db.md) 明确没有建立p95因果，也不能补出任一版本的整服wall MSPT/TPS或精确分配率。只有已结束的报告计入；仍在途的附加回归不提前判定。

MySQL、模组WAL、世界和外部容器是不同事务域。首次内存输入尚未WAL、外部已变更但尚未保存、SQL seal前硬崩溃丢失进程内拆除原因，都保留为明确恢复边界；非干净启动隔离、过期租约、提示ACK和超时不构成退款依据。更多运行/人工恢复要求见 [RECOVERY.md](RECOVERY.md)。
