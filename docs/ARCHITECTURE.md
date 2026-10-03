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

游戏线程处理真实能力、局部缓冲、菜单、票据及已准备结果。默认每 tick 检查 16 个设备、应用最多 64 个完成项、序列化最多 16 个不同栈，软工作预算 2 ms。使用一个子服级 3 工作线程池、一个控制线程、一个定时触发器；队列 128、完成队列 256，MySQL 连接池 4、Redis 池 3。没有按方块创建线程/连接。主线程不等待 Redis/MySQL，不调用同步未来等待；只在停止生命周期进行有界等待，实际最终刷盘/SQL 在专用关闭工作线程中进行。

网络、SQL、WAL/fsync、重试及 Redis 批量发布在工作线程；传入的数据是复制的 Resource 字节、UUID 和不可变快照。注册表感知的 ItemStack/FluidStack 编解码依赖游戏对象，保留在游戏线程且受数量/载荷上限控制，结果按组件缓存。没有异步读取相邻机器或 AE 原生网格对象。

每设备最多一个在途批次，默认间隔 200 ms，活跃端点按轮转检查，空闲指数降低到 2 秒。有界容量和 pending 数量满后能力接口返回剩余/零，产生背压。后端队列超过 3/4 时先延后常规轮询，为注册、关闭和管理操作保留队列余量。每批 SQL 仍处理多个实际资源记录，不能把“一个批次”当作“一条数据库语句”。

相邻物品/流体/FE 交换使用 BlockCapabilityCache；每轮至多一个侧面和各一个外部槽，不主动加载邻区块。SEND 自动抽入；RECEIVE/BOTH 只自动输出本地 RX。外部明确返回的部分剩余归还原领取凭证，重复归还拒绝；异常导致无法判定的外部动作隔离，不能把异常当作零交付后重试。票据恢复/变更每 tick 默认最多两个；单次 Minecraft 强制加载本身可能超过软预算，2 ms 不代表引擎加载的硬上限。

## 持久化协议

本地能力接收首先成为内存 TX，下一批把所有可接受 raw 槽变为带原频道/业务 ID 的不可提取 pending，然后写原子检查点（临时文件、fsync、atomic rename、目录 fsync）。**能力方法成功不代表这次新输入已经独立落盘**，这个窗口与外部机器保存不原子，崩溃时采取隔离。

发送 WAL 先于 SQL DEPOSIT；SQL 在同一事务内验证实例/权限、记录幂等流水、增加余额和 outbox。确认前不释放 pending；数据库已提交而确认丢失时，用同一 ID 重试核验，不超时退款。目的端先独占划拨，再写含该凭证的本地 WAL，之后 `markLocal`，最后游戏线程验证注册表和应用可取额度。Redis ACK 只表示提示已登记，不表示资源到货或外部容器已安全保存。

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

V001/V002/V003 位于 `src/main/resources/db/migration/`。迁移为校验和版本化；GET_LOCK 同连接持有，APPLYING 状态遇到中断必须人工核查 DDL，不自动清库或重复危险 DDL。真实三方并发空 schema 迁移和中断 DDL 测试已有覆盖。

## 数值与输入上限

物品/流体包括完整 Data Components，通过目标 1.21.1 registry-aware CODEC 及命名注册 ID 序列化，不保存运行时数字 ID。资源载荷上限 65536 字节，深度 32、节点 4096、列表 1024；解码 NBT accounter 262144 字节，不使用任意 Java 对象反序列化。当前不压缩，因而没有解压炸弹入口。缺失注册表/组件无法解析时隔离，不替换为空气。

能量、化学品和余额使用 checked signed long/MySQL BIGINT，所有加法/乘法溢出拒绝。FE 的外部接口严格 int，GT 以 V×A 受检乘法和已接受安培结算。测试涵盖大于 2^53、接近 Long.MAX_VALUE 和溢出拒绝；Redis 不保存真实数量，也不参与浮点整数结算。热采用微焦耳 long 加小于一个微焦耳的残差，拒绝 NaN/Infinity 和非法容量。

原版地图及嵌套 map_id 禁止传输，超立方体本身也禁止进入通道。依赖原世界外部引用的其他模组特殊物品没有普适自动识别：运营者应使用白名单/黑名单，AE spatial/外部数据库存储类物品需要独立审查。普通 container component 内嵌物品保持完整，但不代表这些特殊外部引用安全。

## 保留和背压

新业务 ID 使用 UUIDv7 时间窗口：已存在 ID 先核验，未知 ID 超过 30 天或未来偏差超过一分钟拒绝创建新资产。每子服默认 500000 条资源/热历史准入上限，在同一事务里增加计数；满载回滚资产变更并背压。每分钟最多清理 512 条超过 30 天的终态 v7 流水；发布 outbox/inbox 7 天、关闭邀请 30 天、已解决隔离/审计 180 天。

未解决隔离、活资产、未发布 outbox、旧 UUIDv4 幂等及端点 tombstone 不自动丢弃。它们需要协调备份/归档；不能把无限保留称为已实现全数据库无限运行容量控制。当前历史准入有界，持久元数据/tombstone 的完整生命周期归档仍是维护工作。磁盘接近阈值时暂停输入，保留世界+WAL+SQL一致备份后处理，禁止直接清表。
