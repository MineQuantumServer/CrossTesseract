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
