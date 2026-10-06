# 崩溃边界与恢复

MySQL 事务、本模组 WAL、Minecraft 区块存档及第三方机器存档是不同事务域。Redis/MySQL 可靠提交不能使任意外部机器与整个世界原子保存。可信运营方管理员可改库、二进制和世界文件，本项目不宣称防御恶意管理员。

## 可保证的范围

- SQL 余额加减、独占划拨、事务性 outbox、成员和配额在真实 MySQL 中具备并发控制/幂等，资产不会因为多接收端而广播复制。
- 本模组检查点保存自己的发送 pending、接收凭证/剩余量和热状态，原子替换、fsync、校验、代次/版本检查；旧工作提交受 fencing 限制。
- 新实例检测非干净退出后，将该子服 ACTIVE 端点置为 `QUARANTINED / unclean_external_io`，停资源能力和加载票据，保留资产/持久配额，不自动退款或重放。
- 正常停服先停调度/票据、等待有界在途任务、后台写最终本地/SQL检查点；Minecraft 完成世界保存后的 ServerStopped 才写 clean_stop。保存耗时导致租约过期或检查点失败则保持非干净停止，需要恢复。
- 拆除、爆炸和搬运在 SQL 封存确认后保留 SEALED 记录。未收到封存确认不能当作已封存；确认为空的封存端点可退休，有资源时必须审查并按原频道回收，不能把掉落方块作为可重复兑现资产。

## 无法原子覆盖的窗口

源箱子被抽取但尚未保存，远端已收到，源服崩溃后旧箱子可能恢复资源。消息幂等只防止同一 DEPOSIT 再入账，不能删除原版旧箱子中重现的物品。非干净启动隔离端点使其不能继续跨服流通，但源箱子的实际内容必须人工比对或用支持事务的专门适配器。

目的箱子收到资源但尚未保存，数据库/本模组可能已记录扣减，随后崩溃会使箱子回退。不能推断“未确认就是未交付”而退款；不能重放不确定外部提取。本模组保留相应日志和 SQL 凭证供诊断，隔离资产与外部内容后由运营者决定。没有自动让所有其他模组存档加入原子事务。

新接受到本地内存、尚未首次 WAL 的输入也存在掉电窗口；无论上游是否保存，其可恢复性都不能只凭 setChanged() 保证。单服手工回档、磁盘故障或管理员编辑可能超出当前 checkpoint 检测能力；尤其 world+WAL+SQL 同时回退且外部资源未一起回退时，不能自动证明无复制。

## 实测故障

当前68f32db fast模式（两个开关均true）的 [五halt](../reports/faults-68f32db-fast.json) 已实际结束：after_send_wal、after_deposit、after_allocation、after_receive_wal、after_local_sql各一次halt(97)，重启后核对新epoch隔离、WAL/SQL所有权保留与不按超时退款。after_deposit在SQL提交后中断进程，不是人为切断COMMIT应答网络；这些fixture没有覆盖多端点/多publication分组的部分组提交中断或第三方存档回退。

同模式 [恢复/Redis](../reports/recovery-68f32db-fast.json) 已实际验证正常重启恢复合法ticking票据、实际停止Redis时撤票但保留配额、重启/FLUSHDB不删权威配额，以及硬kill Minecraft后新epoch隔离且不恢复旧票据。当前回归的来源声明按运行套件源码/启动归档核对，不能外推其他配置或独立classloader认证。

同模式 [MySQL实际停止/重启](../reports/mysql-68f32db-fast.json) 也已完成：测试耗时7.918233秒，停库快照实际票据0、持久名额1、新设备批准0，恢复票据1。故障中一次管理RCON应答0.980320ms，内容为database_unavailable，表示拒绝与响应而非数据库操作成功；故障errors=1与末尾累计errors=2保留。该次短故障不证明全部连接/COMMIT模糊结果或任意长期断网恢复。

## 当前回退验证与保留的失败证据

[extra父序列](../reports/optimization-extra-sequence-68f32db.json) 因后续回退验证器失败而保持FAILED；它之前原87/B68/C68各三次真实混合窗通过，子报告SHA和功能结果独立保留，不能互相改写。首轮回退在fast_prepare_positive_assets，strip丢失合法FE空HEX列后终止，尚未切换配置。[首轮只读审计](../reports/optimization-restart-fallback-first-failure-audit.json) 确认实际输入128 FE、输出0，SQL余额0/独占LOCAL128与校验通过的同凭证WAL镜像128一致，有效资产总计128，不把镜像相加为256。保留该fixture，修复测试使用新UUID，不重放原输入或按验证失败退款。

[第二轮](../reports/optimization-restart-fallback-68f32db-20261006T194856Z-b6a7c332.json) 已实际同世界正常true→false重启，新same/cross各189 FE输入与实际输出，重复提取0；但quiet观察先读取SQL checkpoint8、后读取WAL10而失败，[续跑父报告](../reports/optimization-resume-extra-68f32db-20261006T194822Z-c221422a.json) 仍EXIT1，不能称完整回退通过。[停止后的新fixture审计](../reports/optimization-restart-fallback-second-failure-assets-audit.json) 确认合计378 FE真实输出，SQL/WAL有效余量0；[原128审计](../reports/optimization-restart-fallback-after-second-failure-audit.json) 仍为原凭证LOCAL128、WAL剩余128、输出0。原资产身份与剩余量保留不表示WAL字节不变：正常注册/关闭已推进revision。

[第三轮完整回退](../reports/optimization-restart-fallback-68f32db-20261006T195817Z-df658dc1.json) 已实际EXIT0，文件SHA-256为 `e3108df183e4cc1793311ed4c22d38480738188eb4bb4d148191795ff0d0f292`；[控制器](../reports/optimization-final-fallback-controller-68f32db-58fcc66e.json) 记录功能通过与正常停服。冻结68核心及相同server/world身份经历三次boot、两次配置切换，完成true/true→false/false→true/true正常同世界重启。同服不同区块和A→B两个新频道各实际输入189 FE，先提取53、保留LOCAL75与共享pool61；关闭的接收能力提取0，重新开启后实际提取136，重复提取0，最终SQL pool/owned与本地/WAL余量0。返回fast后再次提取0，未重放旧输入。

完整回退观察中保留一次checkpoint-only偏斜；检查器在固定期限内等待完整资产/身份/检查点条件收敛，再要求连续quiet，偏斜重置观察计时而不修改SQL或WAL。原始读区间仍保存，不将跨时刻读当作原子快照。[第三轮后原128只读审计](../reports/optimization-restart-fallback-after-corrected-audit.json) 确认原凭证SQL LOCAL128、校验WAL镜像剩余128、实际输出0，有效资产128，不相加。两次失败和原父FAILED继续保留。这些正常重启与审计不证明运行中热切换、旧二进制混跑或任意外部保存回退的原子性。

关闭两开关的全新fixture也已结束：[legacy父报告](../reports/optimization-final-regressions-legacy-68f32db.json) 实际EXIT0、passed、无stop_failure，SHA引用的 [三服七项检查](../reports/three-68f32db-legacy.json) 与 [拓扑五case](../reports/optimization-topology-final-legacy-68f32db-20261006T200139Z-541bf9.json) 均通过。三服76000 FE、144 item、6000 fluid为最终接收缓冲观察，仍有正RX，未全部外部提取；末STATUS A/B/C累计errors=0/1/2、db_deadlock_retries=1/1/0保留。随后拓扑窗口新增错误/拒绝/隔离/死锁重试为0，先前累计值不归零。此false/false套件没有重跑五halt或Redis/MySQL故障；这些故障实测归属上文fast配置。

## 历史实测故障（55）

以下55版记录继续作为历史证据保留：

`reports/recovery-55d87e9.json`：在 `55d87e9` 实际执行正常重启主动恢复合法 ticking 票据、Redis 停止撤销实际票据但保留配额、重启/FLUSHDB 不丢配额、SIGKILL 后新 epoch 隔离并阻止旧恢复、远程关闭完成确认。通用报告名会被后续复测更新，应按版本报告核对归属。

`reports/faults-55d87e9.json`：在 `55d87e9` 的发送 WAL 后/SQL 前、DEPOSIT 后/确认前、独占划拨后/目的 WAL 前、目的 WAL 后/LOCAL 前、LOCAL 提交后/内存应用前以真实 JVM halt(97) 注入。检查 WAL/SQL 的资源阶段、隔离和不可提取，不按超时退款。脚本先保存设备身份，随后故意不保存传输动作，区分身份恢复与外部资源保存问题。这些结果不等于对任意第三方箱子回档的证明。

上述两份55报告不替代当前68结果。68f32db的注册恢复、WAL/SQL确认异常与关闭重试另由13项基础原生及八组合132次执行验证，见 [TESTING.md](TESTING.md)；其中checked SQLException注入不是真正停止数据库，实际停库证据使用当前独立MySQL报告。

## 恢复流程

1. 停止相关端点的实际机器输入/输出；保留隔离，不让它自动继续运行。
2. 备份整个群组的 SQL、所有相关 world 和 `cross_tesseract/` 日志；导出 trace、checkpoint 和外部容器保存证据。
3. 用 `/ct admin trace endpoint <uuid>` 与 `transfer`/`quarantine` 查看具体状态，核对原频道、金额、epoch、版本及已知外部动作。
4. 明确外部保存不确定性后，管理员可以带当前 endpoint version 及 `ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY` 执行 recover；这是人工确认风险，不是程序自动证明完整性。
5. 拆除封存回收用 `reclaim-sealed`：要求端点已卸载、原世界/WAL一致、无有效加载授权及未完成热动作；已提交发送凭证不重复入账，未提交 TX 和未消费 RX 只回到各自捕获的旧频道，退休旧实例。操作幂等且审计。当前含热量/残差的封存回收拒绝自动处理，需专项核查。
6. 没有确认旧服资格已失效时，关闭停留 `REVOKING`。`release-offline` 要求当前会话和运行租约均已过期（含保护时间），并输入明确确认词，不能直接 delete 槽记录。

## 一致备份和回档

协调暂停所有子服的传输和外部工厂，正常停止各 Minecraft 实例，确认 clean_stop，备份所有世界（含 world-id/WAL）、同一 MySQL一致快照以及部署版本/策略；Redis可重建，不是资产备份。MySQL备份的恢复 generation、服务器 epoch 和端点 checkpoint 必须与世界集合一起保存。

恢复前在隔离环境演练。不独立把某台旧世界接入新数据库继续交易；发现 world-id/checkpoint/generation 冲突保持暂停。迁移服务器身份、更新群组恢复代次需要运营者协调停服及审计 SQL 管理，当前没有一键迁移/备份重基工具。永远保留原快照和导出的审计。不能通过修改 DB checkpoint 数字让错误世界“看起来一致”。

## 两阶段批处理恢复补充

每个阶段提交后超时仍不退款。phase 1 的 SQL 已提交而主线程未处理时，原 TX pending 只能凭原业务 ID核验清理；RESERVED 在合法人工回收前仍由原接收端独占。phase 2 的 WAL 是持久镜像，直到 fresh fenced SQL LOCAL 才允许开放。恢复遇到 WAL 中 RESERVED，需要当前 ACTIVE 端点、原绑定和 RECEIVE 授权，在同一恢复事务确认 LOCAL 后才返回；撤权时拒绝并保留资产供隔离审查。已有 LOCAL 的 WAL 剩余量只允许不大于 SQL 剩余量。零量 tombstone 必须保留到 checkpoint 将 SQL 也变为 CONSUMED，不能先漏掉然后再次发现为未见 allocation。

WAL 的同 revision 不同内容一律 checkpoint_version_conflict；相同内容跳过重写，低 revision 拒绝，不通过“>=”覆盖已有内容。恢复过滤隔离内容会推进本地 revision。没有关闭 fsync、没有 group commit，也没有把临时文件当检查点完成。

已恢复设备卸载时保留 closing 记录，直到在途任务结束和最新 WAL/SQL 刷新完成；同实例再次加载会等待该 Closing 终态，已知 NBT/WAL/SQL 回退继续隔离。未恢复设备保留原 WAL 的规则见后文。关闭期间追加拆除/封存/外部异常要求会再次执行关闭，旧完成不能丢掉升级意图。停止时同时保存 loaded 与 closing 端点；未终结或持久化失败保持 unclean，下一启动隔离，不自动重放。

Closing 的拆除原因是进程内意图，不是独立持久化日志。物理方块已移除、SQL seal 尚未提交时硬崩溃，原 WAL/SQL 资产仍可保留，新 boot 会隔离旧端点，但不能从普通 WAL 自动证明本次拆除或恢复 SEALED 意图；需要传输追踪与管理员审查。历史首轮计时版本 `4cfff0a` 对未恢复设备的封存 SQL 失败还有丢失本地重试意图的边界；后续 `e4057a5` 保留该 closing 意图并有界重试，三个新增原生回归验证瞬时失败、明确缺行和克隆拆除，当前68版沿用该修复。测试结果见 TESTING.md。此修复没有新增持久拆除意图日志，不能把历史首轮计时版本冒称为已修复，也不能声称覆盖封存前硬崩溃。

本轮 after_deposit / after_allocation 钩子在整个第一 SQL 阶段成功提交后执行；该阶段里的多条业务一起原子提交，不能再把钩子解释为“该批只执行一条业务”。配置回退仍使用相同 WAL/SQL 所有权，禁止切回旧二进制来绕过 LOCAL 恢复门。外部箱子/机器保存边界与首次内存输入掉电窗口没有因此消失。

RESERVED 的 WAL 恢复遇到非 ACTIVE 端点时，返回的可用缓冲排除该凭证，SQL 保留独占 RESERVED 所有权；不得通过普通 checkpoint 将它升级为 LOCAL。封存回收将完整凭证校验和 LOCAL 剩余量的单调对账放在回收事务内，RESERVED/QUARANTINED 不接受声称已经消费的较小 WAL 剩余量。只有明确人工确认、封存且版本一致的恢复才可把所有权退回原频道；已消费部分不复活、已提交 TX 不重复入账。

注册读取 WAL 遇到不可自动确认的身份、代次、checkpoint 或载荷冲突时，进入本地 registration recovery 状态，停止每秒重试。未恢复的空缓冲不代表空资产：卸载、拆除和停止不得用它覆盖原 WAL，NBT 也保留已知的较大 checkpoint。拆除可单独封存 SQL 所有权；文件冲突仍需管理员审查，不能靠清空内存或重写版本数字消除。实际原生测试制造 NBT checkpoint 高于 WAL，三秒观察 SQL last_seen 和原 128 FE WAL 均保持不变，能力拒绝输入/输出。瞬时后端错误仍有有界重试；已隔离身份不会因权限刷新自动恢复。

注册恢复本身也产生一个新 revision：恢复后的缓冲可能已排除隔离凭证，而未绑定设备不会进入普通传输批次。注册 worker 因此在主线程发布之前，先将 `restored.revision + 1` 的完整恢复状态写入并持久化 WAL，再提交相同 revision 的 SQL checkpoint。主线程 `LocalBuffer.restore` 推进到完全相同的 revision。这样即使未绑定设备立即存档并崩溃，NBT 不会领先于恢复 WAL。该步骤仍不把被排除的 RESERVED 提升为 LOCAL，也不让较大旧 remaining 覆盖新消费。发现这一窗口的失败日志 `logs/optimization-recovery-test-final.log` 保留；当时55d87e9修复后的真实恢复结果在 `reports/recovery-55d87e9.json`、`logs/optimization-recovery-durable-final.log`。

SQL 连接异常可能发生在新的恢复 WAL 已落盘、主线程尚未恢复之间。这时设备仍未注册，内存默认状态不是资产快照；卸载等待在途注册终态后，保留 WAL 并结束本地 closing，不提交空检查点。正常停机也跳过未注册的缓冲，拆除或隔离的 SQL 意图单独处理。只有主线程恢复缓冲与热状态都成功，才标记 registered；失败不让半恢复缓冲进入保存或能力输出路径。

关闭记录的准入受载入上限约束。已准入的 loaded/in-flight 原对象保留关闭容量；对没有当前记录的未准入对象，若 loaded 与 closing 总数已经达到上限，不再新增 Closing，不修改原 WAL/SQL，记录 endpoint_load_limit 拒绝并保持 unclean。此情况是待管理员审查的未确认拆除或隔离，不是封存成功、资源重试或退款；应保留日志，按原端点和 WAL/SQL trace 核对。相同 UUID 的另一个 BE 对象不得通过卸载或拆除移除原对象的票据、调度或封存原 SQL 所有权。

未恢复端点的 SQL 意图失败会保留 Closing 重试，且不会提交默认缓冲的 WAL、checkpoint 或空设备退休。只有 fresh fenced 锁读明确返回端点不存在、已知 checkpoint 为零、WAL 读取为空且 .ctj/.pending 均明确不存在时，才可确认没有该端点资产并结束关闭；注册提交后确认失败不能据此推断缺行。Closing 中尚未提交的拆除意图仍只在内存：SQL 封存前硬崩溃可能丢失该意图，新启动隔离不等于恢复 SEALED 状态，需管理员审查。本节没有新增持久拆除意图协议。

## 死锁与批次重试修复（75392af）

真实500/1000端点复测发现历史桶的共享锁升级死锁，完整InnoDB现场保存在 `reports/optimization-scale-e4057a5-innodb-status.txt`。MySQL整事务回滚会同时使savepoint失效；旧 `finally releaseSavepoint` 的1305异常覆盖1213，导致原有限重试没有识别死锁。现在savepoint使用try-with-resources，已有原异常时，释放失败作为suppressed异常保留，外层rollback清理也不替代原始错误；1213/40001仍按原有有限退避重试，同批业务ID保持不变。

历史容量行首次访问改用无增量的 `INSERT ... ON DUPLICATE KEY UPDATE used=used`，直接取得排他锁，随后仍执行有界条件增量与同事务回滚。没有取消历史容量、余额锁、权限或fencing。真实MySQL回归制造事务内savepoint死锁，确认原始异常被识别、清理异常被保留以及两份变更各提交一次；这不是证明所有死锁都消失。提交确认不明确仍查询原业务记录，不按超时退款。

干净但SEND已关闭的pending仍保存在原WAL/内存资产阶段，不再反复安排没有可发送记录的SQL工作；dirty检查点、恢复状态与重新开启SEND仍会正常调度。OFF不删除或退款资源。
