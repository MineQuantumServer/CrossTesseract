# 部署与实例身份

固定测试版本：Java Temurin 21.0.8+9、Minecraft 1.21.1、NeoForge 21.1.252、MySQL 8.4.7、Redis 7.4.6。其他 MySQL/Redis/NeoForge 小版本尚未验证。Minecraft 客户端安装本模组及服务端实际使用的可选模组依赖闭包；玩家不需要、也不能获得数据库地址和凭据。无需资源代理插件。

## 运营部署

1. 使用 NeoForge 21.1.252 官方 installer 建立每台独立的专用服务端，接受 EULA，安装构建产物到 `mods/`。
2. 从 `config/cross-tesseract.properties.example` 创建该服务端的 `config/cross-tesseract.properties`，启用后端。
3. 相同群组使用相同 `cluster.id`、MySQL schema 和 Redis 服务；每个子服配置不同且长期稳定的 `server.id`。
4. 使用 `CT_MYSQL_URL`、`CT_MYSQL_USER`、`CT_MYSQL_PASSWORD`、`CT_REDIS_URI` 环境变量外置凭据。客户端资源和网络包不含这些字段。不要把真实凭据提交到仓库。
5. MySQL URL 使用 `sslMode=VERIFY_IDENTITY` 并配置受信 CA。Redis 使用 `rediss://`，实现启用了 TLS 主机名校验，CA 由 Java truststore 提供。开发脚本的明文 loopback 配置只适用于本机测试。
6. 防火墙只允许可信运营子服访问后端；不要向玩家开放 MySQL/Redis/RCON。`deploy/compose.dev.yml` 是本机开发配置，不是公网生产配置。
7. 首次使用具有 CREATE/ALTER/INDEX 及本项目表 DML 权限的迁移账户启动一台服；确认迁移后再启动其余服。代码也支持并发迁移，以 MySQL advisory lock 串行化；不会自动删除或重建表。受限长期账户可以不保留 DDL 权限，但新增 schema 版本时需安排迁移窗口。
8. 使用 `/ct admin health`、`/ct admin policy` 检查后端、群组政策、待发布 outbox、隔离和版本；出现不兼容配置时暂停参与。

## 身份和 fencing

`cluster_id` 隔离群组；`server_id` 是子服稳定身份；`world_id` 位于 `<world>/cross_tesseract/world-id`；每次启动产生新 `boot/session_id`，MySQL 原子递增 `fencing_epoch`。重要事务验证 boot、epoch、world、backup generation 和有效租约。Redis 锁/心跳不是 fencing 的权威。

同一 `server_id` 同时加入时，第二台被 `duplicate_server_id` 拒绝。该错误不影响已合法运行的原实例。不要靠改名绕过冲突后直接复用旧世界资产。世界迁移和备份恢复见 RECOVERY.md。

玩家 UUID 来自 `ServerPlayer`，客户端无法提供配额承担人或频道主人。玩家名不参与资产主键。代理群组必须正确配置可信身份转发、后端访问控制和在线认证；本模组不把不可信代理环境的离线 UUID 当作权威身份。本次测试未通过真实代理进行在线身份联调。

加入时协商协议 1、资源格式 1 和稳定能力标识。不支持某兼容类别的子服不会领取该类别；频道中该资源保留完整，共同支持的基础资源可继续使用。装了版本不兼容的模组会由 NeoForge 可选依赖版本约束拒绝启动，区别于完全没安装。

各子服与数据库保持时间同步。业务 ID 的过期/未来偏差校验和 SQL 保留策略依赖合理的时间配置，租约以数据库时钟和本服单调计时共同限制。群组 ID 建议只用小写 ASCII，各服采用完全一致的大小写；默认 MySQL 排序规则不能用仅大小写差异建立独立群组，应使用不同标识。

## 群组政策

首次建立群组时把 `chunkLoading.maxPerPlayer`（默认 2）、频道数（32）、频道端点数（256）写入 MySQL `ct_clusters`。以后 MySQL 为权威；本地配置不一致不会最后写入覆盖。配额下降先运行 `quota-plan` 查看，再用带政策版本的 `quota-policy` 明确确认。按每玩家固定槽号保留较小槽号、撤销超出新上限的槽位；撤销确认前仍占原槽。

运行中会刷新权威配额展示。政策更新后同步修改各服本地配置，安排协调重启；单台改大不能突破 SQL 配额。缓冲、工作预算、兼容开关为各服启动配置，可不同，但降低容量不会删除原库存；新接收应符合容量并有背压。

## 本地开发的可复现启动

`scripts/setup-dev.py` 不覆盖已有文件；默认生成 A/B/C、性能服配置。`start-dev.sh` 使用 Gradle 生成的真实 NeoForge launch scripts。保持终端/监督进程运行，不要使用会在结束时清理子进程的临时 shell 作为服务器监督器。RCON 测试只允许本机可信访问；关闭过程不再发 RCON 查询，避免 vanilla shutdown 与 RCON 等待的死锁窗口。
