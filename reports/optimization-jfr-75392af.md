# 1000端点匹配子窗口的离线JFR证据

当前ACTIVE的主线程采样更集中在频道唤醒路径，实际调用栈指向重复集合构造、接收空间查询和就绪登记。这个结果支持下一轮优先测量这些路径；它不能把Runtime tick p95的363.25%回归分解为各方法耗时，也不能证明某一方法是唯一原因。以下均从已经解析的JSON派生，没有在当前三服计时期间重新读取JFR、运行JDK或在线查询。

输入为 [完整解析JSON](optimization-jfr-75392af.json)，6,202,886字节，SHA-256 `5f24e60d48f414669771cc85802fe17170a35ba276e366739bb2d22df9489d04`。Java流式读取于2026-10-06 15:48:31–15:48:35 UTC实际完成，退出0，日志 `logs/optimization-jfr-75392af.log`。小摘要、冻结源码核对和精确数值保存在 [派生JSON](optimization-jfr-75392af-summary.json)。

| 录制 | 原JFR SHA-256（来自已执行读取器） | 实际扫描事件 | JVM PID核对 |
| --- | --- | ---: | --- |
| 原版87bf217 | `456506711b90adecb18f2ff461e6e5bbf88336145f1bf052778ae2ae2f72f6e1` | 160779 | 87854，与原版监测一致 |
| 新版75392af | `6bf315e53ef62da20171dadc1e070b77825a6e7c9221fc78d8d58f12916d3b9e` | 180200 | 332249，与新版监测一致 |

四段均取首次status回复结束至最后status请求开始的半开内区间。这样排除边界请求期间的不确定部分，不重建原版缺失的完整120秒窗口，不纳入设置、切换或预热。首个采样都带有已观察到的reset标记；两份驱动源码的reset均位于五秒预热之后。reset来自指标下降的间接观察，原始RCON缓冲没有body nonce，这两个限制仍保留。

| 录制/状态 | 监测round | UTC起点（含） | UTC终点（不含） | 实际秒数 |
| --- | --- | --- | --- | ---: |
| 原版OFF | 33–92 | 10:01:27.192361 | 10:03:25.189835 | 117.997474 |
| 原版ACTIVE | 95–154 | 10:03:31.192968 | 10:05:29.189854 | 117.996886 |
| 新版OFF | 257–316 | 14:00:20.211519 | 14:02:18.208774 | 117.997255 |
| 新版ACTIVE | 320–379 | 14:02:26.211502 | 14:04:24.208653 | 117.997151 |

日期均为2026-10-06。每段有60个1000端点稳定监测样本。JFR事件范围分别为09:52:38.311485088–10:05:30.573362924和13:51:32.561570130–14:04:24.897678428 UTC，包含所选两段。使用JFR `Instant`与同机监测UTC对齐，没有跨JVM相减nanoTime或插值。监测UTC相对其自身Python monotonic的偏移范围最多0.0117ms；这不是对JFR与观察器绝对时钟误差的独立测量。

事件总数与按类型计数一致，Execution/Native采样分桶与窗口计数一致，保留栈的示例时间落在对应窗口内。两份录制均未记录DataLoss，保留采样未缺栈或截断。相关ActiveSetting在各录制中仅观察到单一值且两份一致：ExecutionSample 10ms、NativeMethodSample 20ms、ObjectAllocationSample throttle 300/s，GC和顶层GC暂停阈值0ms，park/monitor/sleep阈值10ms。元数据没有独立证明每个瞬间都采用该设置，未记录DataLoss也不等于所有执行都被采样。

## 主线程真实采样栈

| 状态 | 主线程ExecutionSample 原版→新版 | 栈含Runtime.tick 原版→新版 | 占该主线程采样比例 原版→新版 |
| --- | ---: | ---: | ---: |
| OFF | 79→107 | 20→38 | 25.32%→35.51% |
| ACTIVE | 149→258 | 36→155 | 24.16%→60.08% |

ACTIVE全JVM ExecutionSample为736→700，主线程NativeMethodSample另为94→92，不与Java执行采样合并。OFF原版只有79个主线程、20个Runtime采样，排序尤其稀疏。ACTIVE也仅为单次录制的36/155个Runtime采样，没有重复统计或置信区间。采样比例和采样数/秒不是CPU毫秒，不能乘采样周期作为实测方法耗时。

新版ACTIVE的 `RuntimeService.wakeChannel` 出现在112个主线程执行采样中，即155个Runtime采样的72.26%、258个主线程采样的43.41%。inclusive计数每个采样对同方法去重。这是所选录制中可见的热点，不能表述为“占主线程耗时72.26%”。下列保留完整栈是具体证据，不是根据方法名推测：

| 样本数 | 第一实际采样UTC | 栈中主要路径（从调用者到叶节点） |
| ---: | --- | --- |
| 9 | 14:02:29.787704581 | tick:320 → wakeChannel:297 → signal:282 → ChannelCoordinator.signal:40 → HashMap.get/getNode |
| 9 | 14:02:29.388517627 | tick:321 → wakeChannel:297 → ConcurrentHashMap.get |
| 7 | 14:03:07.587868558 | tick:321 → wakeChannel:297 → CompatLoader.resources:23 → HashSet构造 |
| 7 | 14:02:41.837498808 | tick:320 → wakeChannel:297 → receiveRoom:32 → received:29 → stream.toList → AbstractPipeline.exactOutputSizeIfKnown |

这些是保留的若干栈桶，不能相加成全部wakeChannel工作；112来自完整inclusive计数。新版Runtime内的叶方法还包括HashMap.getNode 24、ConcurrentHashMap.get 21、HashMap.getOrDefault 18、HashMap.putVal 14、HashSet构造12、AbstractPipeline.exactOutputSizeIfKnown 11个采样。这些集合/流操作可分布于多个上层调用，不能只凭叶名称把所有采样归给wakeChannel。

冻结75392af源码核对显示：wakeChannel第297行遍历该频道端点，每个端点调用 `CompatLoader.resources()` 并创建stream；resources第23行重新构造HashSet和不可变Set；receiveRoom第32行调用received第29行的stream/toList。tick第320/321行处理远端提示与本地dirty频道，wakeChannel遍历内部没有tick deadline检查。代码结构与采样栈吻合，也说明2ms预算是阶段之间的软检查；本记录未测一次频道唤醒的耗时、访问端点总次数或它与每次超预算tick的对应关系。

原版ACTIVE保留栈包含维护授权回调、旧transfer完成回调的same检查、相邻能力查询和缓冲快照，没有新版wakeChannel方法。只有36个Runtime采样，不足以把旧版各路径稳定排序。新的前台调度工作是有证据的调查方向，不是已经通过对照关闭或实验干预证明的p95因果。

## GC与分配采样

| 状态 | 顶层GC暂停事件 原版→新版 | 暂停总ms 原版→新版 | 最长暂停ms 原版→新版 |
| --- | ---: | ---: | ---: |
| OFF | 3→2 | 10.357265→5.645443 | 5.447664→3.631631 |
| ACTIVE | 35→36 | 90.085517→109.186446 | 6.997081→7.016379 |

以上仅相加 `jdk.GCPhasePause` 顶层事件；没有把Level1/Level2/parallel子事件再累加。ACTIVE `jdk.GarbageCollection` 的28/29个整个周期合计约2494/2488ms，其中G1Old含并发阶段，不能称为2.49秒主线程停止。暂停总量上升约19.10ms、最长暂停变化约0.0193ms；没有逐慢tick关联或滚动2048样本的精确时间轴，不能声称GC解释363.25%回归，也不能完全排除GC/调度对个别tick的贡献。

| 状态 | 栈含主线程Runtime的分配样本 原版→新版 | 该条件下权重估计MB 原版→新版 | 全JVM权重估计MB 原版→新版 |
| --- | ---: | ---: | ---: |
| OFF | 77→89 | 33.191→67.962 | 351.592→348.053 |
| ACTIVE | 268→3096 | 83.128→1635.832 | 6376.703→5438.078 |

MB为1,000,000字节，精确权重在JSON。ACTIVE主线程Runtime条件下的估计权重约19.68倍；全JVM估计权重反而下降14.72%。这支持分配采样向主线程Runtime转移，不能称为整个JVM分配爆涨。保留的新版MAIN类目包含HashMap节点/节点数组、Object数组、ReferencePipeline.Head、HashMap和IteratorSpliterator，与所见集合/stream执行栈一致。但类目仅是读取器按全体角色样本数保留的top25子集，没有按Runtime条件保存完整分配栈/类目账本；不能把1.636GB全部分配给wakeChannel，也不能当作精确对象分配率或存活堆。

定期CPULoad数值及阈值以上的park/sleep事件也保存在解析JSON。这些是全JVM/机器的周期指标或有阈值的持续事件，不是主线程耗时；并发线程等待不能相加成窗口wall time。跨窗口边界的持续事件已排除，排除计数保留。10ms阈值未覆盖本次2–3ms级tick开销，不能以未看到等待事件证明没有短等待。

## 来源与结论边界

源码位置按录制的冻结来源限定：原版 `87bf217fcaffcceb2629c36bb54d5158b9f461e8`，新版 `75392af252744f240253d134d1da565a49b2cc9f`。已用git show核对选定实际正行号及相应源码SHA；没有把原版行号映射到当前文件。`source_path`由二进制所属类推导，隐藏lambda的动态类名和-1行号不代表可定位的源码声明；JDK/第三方叶帧不是本模组源码。source_revision是已声明冻结来源，旧测试框架没有class-loader级来源证明。

1000端点p95 0.576145→2.668976ms来自另一份Runtime滚动最多2048样本报告，不与本JFR约118秒区间严格同窗。当前没有逐tick持续事件、每次唤醒/捕获/完成阶段的实测持续时间、精确分配率或慢tick与GC的关联。因此这里只确认可见热点与分配采样变化，把重复资源集合/空间查询/就绪登记列为下一轮测量候选；不计算363.25%回归中的方法百分比，不声称已找到唯一原因，也不外推整服wall MSPT、实际TPS或真实工厂容量。

本轮没有修改Java模组核心、预算、测试驱动或计时现场。
