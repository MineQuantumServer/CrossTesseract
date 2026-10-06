# 68f32db JFR离线采样证据

仅从已经解析的JSON生成本摘要，没有重新打开JFR或运行JDK。68的ACTIVE窗口主线程执行样本169个、含Runtime.tick的样本72个、含wakeChannel的样本35个；753/9258相应观察数更高，但这些采样计数不能换算CPU毫秒或认定为主线程p95变化的因果解释。

主输入 [已解析JSON](optimization-jfr-68f32db.json)，执行解析时间 `2026-10-06T17:02:58.146602Z`；其SHA-256为 `84e3ce149d7f4b60cc763f6c8ad781cd458b0bdb17d6b0bfb907a104c5cc74b0`。四窗口、事件统计、实际栈、冻结源码行、历史解析输入SHA见 [摘要JSON](optimization-jfr-68f32db-summary.json)。原始JFR的文件摘要仅继承读取器证据，本次没有重读原始文件。

## 时钟与四个实际窗口

只选择1000端点reset后60点的保守内区间：[首status回复结束，末status请求开始)。每段约118秒，不是名义120秒。JFR Instant与同机观察器UTC对齐；没有相减跨JVM单调钟、插值或将建立/预热混入。记录中的JVM PID均与监测器一致，所选四窗覆盖完整，没有记录DataLoss事件；这不证明每次执行或每次分配都被采到。

| 来源/模式 | 真实UTC区间（2026-10-06） | 内区间秒 | 全线程Execution / Native事件 | 主线程Execution / Runtime样本 |
| --- | --- | --- | --- | --- |
| 原版87 OFF | 2026-10-06T10:01:27.192361Z–2026-10-06T10:03:25.189835Z | 117.997474 | 107 / 5862 | 79 / 20 |
| 原版87 ACTIVE | 2026-10-06T10:03:31.192968Z–2026-10-06T10:05:29.189854Z | 117.996886 | 736 / 5849 | 149 / 36 |
| 68 OFF | 2026-10-06T16:58:35.002711Z–2026-10-06T17:00:32.998949Z | 117.996238 | 94 / 5859 | 85 / 27 |
| 68 ACTIVE | 2026-10-06T17:00:41.003290Z–2026-10-06T17:02:38.998987Z | 117.995697 | 668 / 5847 | 169 / 72 |

ExecutionSample、NativeMethodSample分别统计；当前主线程Native样本90/116均在Thread.yield0路径且无Runtime.tick栈，不能与执行样本合并成Runtime耗时。当前OFF仅27个Runtime样本，稳定热点排序或p95归因证据不足。设置是全记录观察值：执行采样10ms、native20ms、分配节流300/s；采样时长/事件阈值不能用于反推精确CPU耗时。

## 1000 ACTIVE历史采样比较

| 冻结来源 | MAIN Execution | Runtime inclusive /MAIN | wakeChannel inclusive /Runtime | Runtime分配权重MiB（事件） | 全JVM分配权重MiB | 顶层GC暂停次数 /总ms /最大ms |
| --- | --- | --- | --- | --- | --- | --- |
| 87bf217 | 149 | 36 / 24.16% | — | 79.28 (268) | 6081.30 | 35 / 90.085517 / 6.997081 |
| 75392af | 258 | 155 / 60.08% | 112 / 72.26% | 1560.05 (3096) | 5186.16 | 36 / 109.186446 / 7.016379 |
| 9258a6a | 233 | 109 / 46.78% | 79 / 72.48% | 101.68 (501) | 3854.11 | 48 / 127.417854 / 6.757546 |
| 68f32db | 169 | 72 / 42.60% | 35 / 48.61% | 70.14 (377) | 3840.99 | 42 / 138.914355 / 7.861690 |

inclusive方法计数彼此可重叠，不能相加；wake计数来自保存的排名项，未出现的项不补为零。分配weight是JFR统计估计，不是精确bytes/对象数、保留堆或某方法独占分配。68 Runtime ACTIVE估计权重相对原版 -11.52%，全JVM -36.84%；样本数量和权重会有抽样变化，不能据此认定资产路径或CPU成本降低了相同比例。

## 实际保存的68调用栈

当前ACTIVE最常见Runtime栈之一为 `ConcurrentHashMap.get → RuntimeService.wakeChannel:298 → tick:327`（9样本）；直接leaf在wakeChannel:299的一栈4样本；`HashMap.getNode → ChannelCoordinator.hasPendingSignal:63 → wakeChannel:302 → tick:328`的一栈3样本。这些栈支持剩余探测包含端点lookup、状态判定和已有ready信号查询；没有证明某个方法独占全部开销。

当前MAIN含Runtime栈的leaf中，ConcurrentHashMap.get14、HashMap.getNode12、wakeChannel9、HashMap.getOrDefault6样本。MAIN整体leaf仍包含ChunkHolder.getTickingChunk41、ChunkMap.processUnloads15，不能把主线程全栈活动归到模组。回调派发lambda$submit$10的inclusive排名13样本也保留；没有把所有lookup或回调都自动归到wakeChannel。

所列方法/行均按冻结 `68f32db` 的记录line table和git文本核对，具体源码摘要/行文本见summary的source_checks。历史栈仅对应各自87/753/9258冻结源；隐藏lambda类与负行号不当作独立声明行。启动归档、源码/类摘要和PID不是class-loader CodeSource证明。

## GC与归因边界

68 ACTIVE顶层GC暂停42次、总138.914355ms、最大7.861690ms；原版35次、总90.085517ms、最大6.997081ms。这里仅累加同一顶层GCPhasePause事件，不相加嵌套阶段。GarbageCollection总2977.388473ms包含并发生命周期，不能称为主线程暂停；边界跨越的duration事件已排除。OFF顶层暂停8.848002ms对原版10.357265ms，样本少，不能当作稳定GC优化。

记录显示采样栈分布、分配权重和GC活动不同，但没有每tick时间与样本/GC对齐的因果数据。规模报告中68主线程p95仍相对原版升38.42%/36.56%/102.46%；本JFR不把采样减少解释成精确p95收益，也不能断言GC造成或解释该回归。已有Runtime滚动分位和Minecraft记录工作平均都不是完整wall MSPT/实际TPS；一次固定供给、单JVM和一次重复不证明工厂容量或三服性能。

9258的首100旁路监测缺口和原版完整窗DB初值缺失仍保留在 [四版本规模比较](optimization-scale-comparison-68f32db.md)，不影响本页仅选双方都有真实记录的1000 OFF/ACTIVE内区间。没有在线SQL/RCON、运行MC、修改Java或增加现场负载。
