# 管理、诊断与安全恢复

管理员命令要求服务端 permission level 2；政策修改要求 level 4。控制台也可使用，审计 actor 为零 UUID。命令执行后显示处理中，数据库工作在受控后台队列中进行；“状态待确认”不能被解释为可安全退款。

```text
/ct admin health
/ct admin policy
/ct admin metrics
/ct admin trace channel <channel_uuid>
/ct admin trace endpoint <device_uuid>
/ct admin trace transfer <transfer_uuid>
/ct admin trace quarantine <record_uuid>
/ct admin quota <player_uuid>
/ct admin off <device_uuid>
```

`health` 返回当前群组的频道、端点、配额、流水、隔离和待发布 outbox 数量。`metrics` 返回本服状态、实际票据、队列、事务/失败/重试计数，以及滚动样本 p50/p95/p99。`trace` 查询有群组隔离的单个实体，并记录诊断审计；不是公开玩家查询入口。玩家 `/ct quota` 只显示自己的全群组占用和位置。

配额降额先查看确定性预案，再提交当前政策版本：

```text
/ct admin quota-plan <new_limit>
/ct admin quota-policy <new_limit> <policy_version> CONFIRM_SAFE_REVOCATION
```

超过新上限的固定槽进入 REVOKING，不在旧票据未失效时直接释放。随后同步各子服启动配置，协调重启。历史容量修改使用 `/ct admin history-policy <limit> <policy_version> CONFIRM_HISTORY_CAPACITY`；容量不是吞吐承诺，长期高负载需要监控和归档计划。

以下操作必须先保留证据并阅读 [恢复边界](RECOVERY.md)：

```text
/ct admin recover <device_uuid> <endpoint_version> ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY
/ct admin reclaim-sealed <device_uuid> <endpoint_version> ACKNOWLEDGE_EXTERNAL_SAVE_UNCERTAINTY
/ct admin release-offline <device_uuid> CONFIRM_EXPIRED_LEASES
```

`recover` 仅允许本服原世界的隔离端点，版本不符拒绝；它是运营者确认外部存档风险，不自动证明箱子/机器内容一致。被隔离的 SQL 领取凭证不会因为端点恢复而重新成为可取库存。`reclaim-sealed` 要求设备已卸载、世界/代次/检查点一致，无加载授权及未完成热动作；仅按原频道回收明确持有的资产并退休旧实例。热能/残差的封存自动回收尚未支持，遇到该情况拒绝并保留。`release-offline` 只处理已申请撤销且会话和运行租约均过期超过保护窗口的占用。

排查时先看暂停原因和后端状态，再看 endpoint/channel version、boot/epoch、SQL 传输状态和 WAL。后端故障时停止新输入；不要清表、删除 WAL、改 checkpoint 或批量重发。断网恢复后，已过期会话需要新 fencing 启动，不能让旧实例无限续租。

生产凭据不出现在游戏数据包。日志不会打印资源完整载荷或数据库密码；开发异常栈仅在显式测试模式、开发群组内限频启用。开发 RCON/故障钩子不得开放给玩家，生产关闭 `cross_tesseract.testHarness`。

## 合批配置与安全回退

本轮新增的 transfer.channelBatches、transfer.localFastPath、maxBatchDevices/Records/PayloadBytes、activeWakeMillis、idlePollMillis、notificationMillis、limits.readyChannels、diagnostics.transferSampling 均只在启动读取；默认值见 config/cross-tesseract.properties.example。设备数 1–16，记录数 192–2048，载荷 8–16 MiB，默认 8/256/8 MiB。字节/记录同时约束第一阶段和按最新快照拆分的第二阶段；不扩大设备缓冲或历史容量。

安全回退：停止外部输入，正常停服并确认 clean_stop；将 channelBatches=false、localFastPath=false 后使用同一新版 JAR 启动。无需 schema 回退/清库，不重放已完成业务。故障停服仍需按恢复流程审查，不能把开关当资产补偿工具。热/AE 原型的既有开关和语义不变。当前 V001–V004 校验和没有更改。

升级时协调全群组暂停输入、正常停止并检查备份，再在各子服核验相同目标 JAR 摘要后启动。存档/SQL 格式兼容不等于已经验证旧 `87bf217` 与新二进制同时运行；本轮没有验收这种混跑。两个优化开关的回退仅指同一新版的安全路径，不能把旧恢复实现重新接入群组来绕过新的 LOCAL/检查点门。

新增指标包括真实 db_transactions/db_transaction_attempts/db_statements、db_connection_wait_ms、WAL 写入/字节/屏障分位数、batch_devices/records/payload_bytes、queue/execution/apply 等待、ready_channels/devices、completion_admitted、closing_devices、local/remote wake 与轮询/空批/分配 miss、deferred_registry_decodes。db_statements 是经过 Sql helper 的语句数；三服 optimization-benchmark.py 报告另取 MySQL performance_schema 的真实账户语句事件（规模 performance-test.py 没有这项观测）。local_input/output_units 是混合资源的本地端口接受/提取计数，output 含本地明确 remainder 归还之前的提取，不作为成功外部吞吐；使用实际接收容器返回值测吞吐。mc_recorded_tick_ms_avg100 是原生最近 100 个记录 tick 均值；mc_target_ticks_per_second 是配置目标，不能当整阶段实测 TPS。

`local_exchange_calls` 计数的是产生正数量变更后调用 `localChanged` 的次数；不包括所有空探测、模拟或失败的相邻能力调用。`local_credit_publications` 包括跨服来源在本服发布的凭证，单独看它不能证明同服来源的快速命中数量。需要结合测试拓扑、实际输入/输出记录判断。


同一核心68 JAR的正常重启回退已经实测：同服/跨服两个新频道在true/true→false/false→true/true之间保留正余额及原业务ID，各189FE输入/实际输出守恒，重复提取0。具体报告为 `reports/optimization-restart-fallback-68f32db-20261006T195817Z-df658dc1.json`。首两次观察器失败仍保留，并单列隔离开发环境中未提取的128FE资产（SQL状态LOCAL）；不能借此把生产未知外部动作标成已交付。版本/实例不匹配、后端租约过期或非干净停止仍按RECOVERY.md处理。

仅合批模式false localFastPath保留旧的本地交换门：本轮混合资源持续负载下，物品实际输入到目的箱子接受出现明显延迟回归（中位71/78秒，个别超过110秒）。需要物品低延迟时不要只看事务数；完整快速模式缓解该等待，但部分场景增加SQL语句、WAL和主线程成本。配置选择应结合PERFORMANCE.md的全部重复和错误记录。
