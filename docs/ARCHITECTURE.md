# 权威状态与线程模型

## 所有权阶段

```mermaid
flowchart LR
  machine[本地外部机器] --> tx[本地 TX 缓冲]
  tx --> wal[持久 WAL 待提交]
  wal --> balance[MySQL 频道余额]
  balance --> reserved[目的端独占 RESERVED]
  reserved --> rxwal[目的端 WAL]
  rxwal --> local[LOCAL 接收额度]
  local --> remote[目的端外部机器]
```

资源只在一个所有权阶段可用。数据库里的发送流水是凭证，不是第二份库存；已提交但主线程尚未删除的 TX pending 不允许提取。SQL 余额扣减与 ALLOCATE 记录在同一事务完成；多个接收端不会分别领取一份完整余额。共享调度以频道/资源类别需求表和 `last_grant` 公平次序分配，过期/离线/无权需求失效，不建立所有设备两两连接。

游戏线程处理真实能力、局部缓冲、菜单、票据及已准备结果。默认每 tick 检查 16 个设备、应用最多 64 个完成邮箱项（另有最多一个合并维护回调）、序列化最多 16 个不同栈，软工作预算 2 ms。使用一个子服级 3 工作线程池、一个控制线程、一个权限维护线程、一个通知/历史线程和一个定时触发器；队列 128、完成队列 256，MySQL 连接池 4、Redis 池 3。没有按方块创建线程/连接。主线程不等待 Redis/MySQL，不调用同步未来等待；只在停止生命周期进行有界等待，实际最终刷盘/SQL 在专用关闭工作线程中进行。

网络、SQL、WAL/fsync、重试及 Redis 批量发布在工作线程；传入的数据是复制的 Resource 字节、UUID 和不可变快照。注册表感知的 ItemStack/FluidStack 编解码依赖游戏对象，保留在游戏线程且受数量/载荷上限控制，结果按组件缓存。没有异步读取相邻机器或 AE 原生网格对象。

每设备最多一个普通在途批次，常规后台周期默认 200 ms，定向唤醒可按50 ms活跃边界更早排入频道队列；本地相邻交换独立使用主线程预算。活跃端点按轮转检查，空闲权威轮询退避到 2 秒。有界容量和 pending 数量满后能力接口返回剩余/零，产生背压。后端队列超过 3/4 时先延后常规轮询，为注册、关闭和管理操作保留队列余量。每批 SQL 仍处理多个实际资源记录，不能把“一个批次”当作“一条数据库语句”。

相邻物品/流体/FE 交换使用 BlockCapabilityCache；每轮至多一个侧面和各一个外部槽，不主动加载邻区块。SEND 自动抽入；RECEIVE/BOTH 只自动输出本地 RX。外部明确返回的部分剩余归还原领取凭证，重复归还拒绝；异常导致无法判定的外部动作隔离，不能把异常当作零交付后重试。票据恢复/变更每 tick 默认最多两个；单次 Minecraft 强制加载本身可能超过软预算，2 ms 不代表引擎加载的硬上限。

## 持久化协议

本地能力接收首先成为内存 TX，下一批把所有可接受 raw 槽变为带原频道/业务 ID 的不可提取 pending，然后写原子检查点（临时文件、fsync、atomic rename、目录 fsync）。**能力方法成功不代表这次新输入已经独立落盘**，这个窗口与外部机器保存不原子，崩溃时采取隔离。

发送 WAL 先于 SQL DEPOSIT；SQL 在同一事务内验证实例/权限、记录幂等流水、增加余额和 outbox。确认前不释放 pending；数据库已提交而确认丢失时，用同一 ID 重试核验，不超时退款。目的端先独占划拨，游戏线程验证注册表载荷及当前接收空间；再写含该凭证的本地 WAL，之后以当前授权确认 SQL LOCAL，最后主线程应用可取额度。Redis ACK 只表示提示已登记，不表示资源到货或外部容器已安全保存。

RX 部分提取只减少目的端独占额度，下一检查点记录单调递减 remaining；simulate 不变更余额。WAL 版本不允许旧工作覆盖更高版本；检查点校验 SHA-256 和世界/群组备份代次；文件上限 8 MiB。WAL 与 chunk NBT checkpoint 及 SQL 对照，发现已知回退/缺失/代次冲突隔离。`setChanged()` 只请求 Minecraft 保存，不充当立即 fsync。

切换频道由主线程先验证空缓冲、无在途及无热残差，立即暂停能力，再提交捕获的实例/主人/版本/目标频道。成功后等待新权限；失败或结果不明确时，只接受在结果之后开始的权威权限读取来恢复，早已排队的旧回复不能解锁。端点和频道权限版本不回退，陈旧快照不能把新绑定改回旧频道。实际后端 GameTest 验证切换期间 FE 输入为零、旧快照无效和失败后的新查询恢复。

热交换另用 `PREPARED -> COMMITTED` 独占转移。发送准备先从本地保留但池内不立即可取；本地应用及 WAL 后提交。接收准备先从池内扣热，未完成时不能重新分给其他端。仅确实尚未本地应用的取消可以补偿，超时不能取消不确定结果。

## MySQL schema

|实体|表|关键完整性|
|---|---|---|
|群组政策|ct_clusters|cluster 主键、政策版本、配额和恢复 generation|
|子服/当前启动会话|ct_servers|cluster+server 主键、world/boot/epoch/租约/协议能力|
|频道/成员/邀请|ct_channels / ct_members / ct_invites|单一非空 owner、版本授权、成员复合唯一键|
|设备|ct_endpoints|稳定实例、设备主人、世界/位置、绑定频道、epoch/checkpoint/state|
|配额并发锁与固定槽|ct_player_guards / ct_chunk_grants|玩家行锁、cluster+player+slot 主键、设备/请求唯一约束|
|业务幂等|ct_operations|cluster+operation ID|
|规范资源载荷|ct_resources|类别、格式、SHA-256，并再次比较完整字节防止仅靠哈希|
|余额/独占流水|ct_balances / ct_transfers|复合主键、非负 BIGINT、remaining 范围约束|
|公平接收需求|ct_demands|channel+endpoint+kind、TTL、最后分配次序及 EU profile/quantum|
|可靠待发/提示幂等|ct_outbox / ct_inbox|提交同事务 outbox，cluster+server+event 唯一 inbox|
|隔离与审计|ct_quarantine / ct_audit|不确定资产保留，恢复操作审计|
|热池/热交换|ct_thermal_pools / ct_heat_exchanges|独占微焦耳、准备/提交状态|
|定向补货请求|ct_stock_requests|有界持久意图，不持有余额；与既有轮转独占分配器接线|
|AE 原型广告|ct_ae_networks|endpoint、真实本地网格 UUID、租约、controller/activity|
|历史容量|ct_history_buckets|每子服历史行计数与并发条件准入|

V001/V002/V003/V004 位于 `src/main/resources/db/migration/`。迁移为校验和版本化；GET_LOCK 同连接持有，APPLYING 状态遇到中断必须人工核查 DDL，不自动清库或重复危险 DDL。真实三方并发空 schema 迁移和中断 DDL 测试已有覆盖。

## 数值与输入上限

物品/流体包括完整 Data Components，通过目标 1.21.1 registry-aware CODEC 及命名注册 ID 序列化，不保存运行时数字 ID。资源载荷上限 65536 字节，深度 32、节点 4096、列表 1024；解码 NBT accounter 262144 字节，不使用任意 Java 对象反序列化。当前不压缩，因而没有解压炸弹入口。缺失注册表/组件无法解析时隔离，不替换为空气。

能量、化学品和余额使用 checked signed long/MySQL BIGINT，所有加法/乘法溢出拒绝。FE 的外部接口严格 int，GT 以 V×A 受检乘法和已接受安培结算。测试涵盖大于 2^53、接近 Long.MAX_VALUE 和溢出拒绝；Redis 不保存真实数量，也不参与浮点整数结算。热采用微焦耳 long 加小于一个微焦耳的残差，拒绝 NaN/Infinity 和非法容量。

原版地图及嵌套 map_id 禁止传输，超立方体本身也禁止进入通道。依赖原世界外部引用的其他模组特殊物品没有普适自动识别：运营者应使用白名单/黑名单，AE spatial/外部数据库存储类物品需要独立审查。普通 container component 内嵌物品保持完整，但不代表这些特殊外部引用安全。

## 保留和背压

新业务 ID 使用 UUIDv7 时间窗口：已存在 ID 先核验，未知 ID 超过 30 天或未来偏差超过一分钟拒绝创建新资产。每子服默认 500000 条资源/热历史准入上限，在同一事务里增加计数；满载回滚资产变更并背压。每分钟最多清理 512 条超过 30 天的终态 v7 流水；发布 outbox/inbox 7 天、关闭邀请 30 天、已解决隔离/审计 180 天。

未解决隔离、活资产、未发布 outbox、旧 UUIDv4 幂等及端点 tombstone 不自动丢弃。它们需要协调备份/归档；不能把无限保留称为已实现全数据库无限运行容量控制。当前历史准入有界，持久元数据/tombstone 的完整生命周期归档仍是维护工作。磁盘接近阈值时暂停输入，保留世界+WAL+SQL一致备份后处理，禁止直接清表。

## 本轮子服/频道协调与本地低延迟路径

同一个 Runtime 的 channel_id 队列只允许一个有效 lease，运行中收到的 dirty 信号保留；完成后回到频道队列尾。UUID、BE 对象身份、捕获的绑定/version 和当前 SQL 会话共同限制旧任务应用，卸载关闭会等待普通/热任务终结。每个频道没有独立线程或连接池。默认每批最多 8 台设备、256 个完整快照记录、8 MiB 载荷；合法单设备 WAL 最多 8 MiB，因此不允许把批次字节配置降到单设备无法推进的值。

主线程相邻交换不再等普通 SQL inFlight/nextPoll，但热准备/待确认、绑定、权限期限、故障和隔离仍阻止相应操作。默认16次检查下，快速到账队列最多使用一半配额，剩余继续轮转；配置为1次时唯一名额可能被快速队列占用，不能声称保留一半。持续输入仍使用有限 TX 槽、pending 和队列背压。

第一 SQL 阶段 channelBatch 在同一 Connection/事务中复用当前 fencing、频道锁及主人授权，按设备保存点处理 checkpoint、每条原始 deposit ID、需求、一次 JOIN 查询的 outstanding 和全群组公平划拨。事务仍含多条 SQL。坏端点保存点回滚不改变其他端点；1213/1205/40001可有限重试整个事务；其它连接失败先暂停，后续重新发现/核对。原TX业务ID和持久接收凭证保留，新轮需求尝试可生成新的业务ID。发送入账与同批本地公平独占划拨可以在该事务内完成，但不会越过远端合法需求。

阶段间主线程仅应用 committed/consumed ID 增量，保留后台期间新输入和已消费 remaining。新输入获得新的业务 ID；另取新 revision 的完整当前快照，加上尚未开放的新 receipts，后台 fsync/atomic rename/目录 fsync 完成后，再在第二 SQL 阶段 publishBatch 用新授权确认 LOCAL、更新单调 checkpoint。新快照按实际设备/记录/字节重新分组；SQL 事务内不等待 WAL。随后主线程仅添加新 credit，不恢复旧快照 remaining。本地接收端直接排入预算内输出，无需 Redis 绕回。跨服接收端使用同一所有权阶段，通过频道/端点提示或有界权威轮询发现工作。

默认仍按端点 last_grant 公平；不按子服平均、不固定均分、不默认同服优先。SELECT 候选排除无 room、无匹配资源、超过凭证上限、历史准入满、失效权限/实例/格式的端点。共同支持的 ITEM/FLUID/FE/EU/CHEMICAL 进入普通新路径；热仍是独立 PREPARED/COMMITTED 状态机，AE 仍只同步访问本地可兑现 RX，并保留异步定向补货。没有实现原生跨 JVM IGrid 合并。

完成回调在提交 IO 前预留有界邮箱容量，队列满时拒绝新工作，不丢掉已完成资产的终结回调；native 回调异常也终结设备和频道 lease。维护、通知与传输执行器拆开，默认池 4 还以背景连接准入最多 3 留 1 给 control；池 1 配置无法提供连接隔离，失败仍安全暂停。锁依赖仍可让控制事务等待，不宣称无锁竞争。所有缓存与队列有界。

配置回退关闭 transfer.channelBatches 和 transfer.localFastPath 后需要正常停服/重启；关闭优化保留新的权限、恢复门和完成队列安全修复。控制心跳、当前票据授权和配额政策读取共享一个有界 SQL 事务，权限扫描与历史清理独立执行；这减少维护事务但不延长授权期限。尚未完成的实测结果见本轮性能报告，不以设计描述当作通过证据。
