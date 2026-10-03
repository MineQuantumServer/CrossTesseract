# 0.1.0-dev 开发交付与验收记录

本次交付是实际可构建、可安装并已运行的 Minecraft 1.21.1 NeoForge 项目。基础跨服链路、全群组加载配额和三个可选模组适配均有实测证据。**全部需求尚未完成**：AE2 原生跨 JVM 网络/服务合并没有实现，已有默认关闭的真实 managed-node 实验代理；其他未完成与未验证项目逐项列在 [TASKS.md](TASKS.md)。不将实验原型、控制台 fixture 或短性能窗口当作完整生产验收。

本轮继续补齐 AE 五类库存分页、持久定向调货/取消、原生短缺异步补货及 GUI 实测，更新为四版本迁移。源码差异和证据逐项见下文。

## 交付物与构建

- 安装包：`build/libs/cross_tesseract-0.1.0-dev.jar`，4028891 字节；SHA-256 `ccab2954e92e9ba9b4020c6b5b9a22812e2a76503df6cc0aa8039c26189821d7`。
- 源码 JAR：`build/libs/cross_tesseract-0.1.0-dev-sources.jar`；SHA-256 `fa1661299e73a0b26c6126b0d7fc86eb3d8d98831ebfb99591e5a968509ac740`。
- 项目包：`build/distributions/cross_tesseract-0.1.0-dev-project.zip`，包含源码、固定构建配置、脚本、文档、配置示例、JSON 报告、截图及上述两个 JAR。
- 证据包：`build/distributions/cross_tesseract-0.1.0-dev-test-evidence.zip`，包含完整开发测试日志、报告、JUnit XML/HTML、截图及前后 JFR。压缩包校验值记录于 `reports/delivery-artifacts.json`。
- 没有打包 Minecraft/NeoForge 或可选上游模组实现类、世界、数据库、凭据文件、JDK、用户原有文件及参考源码仓库。开发配置中的公开测试密码仅适用于 loopback 隔离环境。

实际成功执行：

```bash
scripts/gradle-dev.sh build -Dct.integration=true
scripts/gradle-dev.sh test -Dct.integration=true runGameTestServer -PgameTestBackend -PtestMods=ae2
```

最终日志为 `logs/stock-final-build.log`，原生补货验证日志为 `logs/stock-ae-tests.log`。构建清单和嵌入库版本见 `reports/build-manifest.json`。全新机器先运行 `scripts/install-jdk.sh`、`scripts/fetch-references.sh`；GT 测试闭包另外按 [COMPATIBILITY.md](COMPATIBILITY.md) 构建。运行时客户端不会连接 Redis/MySQL，也不会接收数据库凭据。

## 固定版本与实际源码

Java 为 Temurin 21.0.8+9，Gradle 9.2.1，ModDevGradle 2.0.148，Minecraft 1.21.1，NeoForge 21.1.252。基础及七种可选依赖组合均有锁文件。

| 指定参考 | 实际分支 | 读取的 commit SHA | 实测版本/许可说明 |
|---|---|---|---|
| Applied Energistics 2 | `1.21.1` | `db17504a86128fdf3dae31f5fb7a112a646e0b93` | AE2 19.2.18 + GuideMe 21.1.1；主项目 LGPL-3.0，API 按文件核对 |
| FortyTwoCn/GregTech-Modern | `1.21` | `c72dc16b52795cbb0456b6e15e13cc4a85c0ed1b` | gtceu 8.0.0；LGPL-3.0 |
| Mekanism | `1.21.x` | `bcd7a8bf594cff9614eb12238fe3776f19da24d9` | 10.7.19.85；MIT |
| SuperMartijn642/Tesseract | `neoforge-1.21` | `cedf6df38a02d1f204733f2d8723d7f99861d972` | 1.0.38；All rights reserved，仅参考交互/视觉语言 |

原始 GT 构建所需 ModularUI `3.3.1-jei19.57-preview1` 无法从公开 Maven 取得。日志 `logs/gt-build.log` 保留真实失败。GT 源码保持上述 FortyTwoCn SHA 不变，使用固定 ModularUI-Modern `8ecb104d0c38b1eb9baab5c837624034db7ca873` 的 3.3.1 本地构建、外置 Gradle init 脚本替代依赖，完整 GT 运行包实际构建并启动通过。替代步骤、API 调查和支持范围见 [COMPATIBILITY.md](COMPATIBILITY.md)。不宣称缺失 preview 的完全相同发布闭包已验证。

NeoForge 文档读取版本化源码 SHA `89528c36e4eb34d46b1de346c045172ce8ca9fde` 的 1.21.1 页面；请求的公开文档 URL 在本环境返回 404。参考仓库均未修改。授权记录见 [THIRD_PARTY.md](THIRD_PARTY.md)。本项目材质、模型和界面为原创，独立命名空间，不要求原始 Tesseract 前置。

## 已实现的实际行为

- 物品完整 Data Components、NeoForge 流体及 FE：本地发送/接收缓冲、能力模拟/部分接收、相邻能力缓存与自动交换、独占划拨、批量异步 SQL/WAL 和背压。双向接收库存不会自动重新发送。
- N 个独立服务端身份：cluster/server/world/boot/fencing、重复实例拒绝、协议和资源能力协商；缺少兼容模组的子服继续使用共同资源。
- 私有频道：唯一主人、成员、跨服离线邀请接受/拒绝/撤销/过期、确认转移、冻结排空删除、服务端权限及版本检查。设备主人与频道主人分别保存，绑定期间立即暂停输入并拒绝陈旧授权回调。
- 全群组加载：MySQL 玩家行锁和固定槽位、幂等请求、票据安装/撤销确认、持久意图和有界运行租约、启动异步主动恢复、确定性降额、安全远程关闭。NeoForge TicketController 只管理本模组 UUID 票据。
- MySQL 四版本迁移、事务 outbox、Redis 按目的子服 Streams、pending/重复/恢复/裁剪后 SQL 补扫、inbox、审计、隔离与带确认词的管理恢复。Redis 不持有独立资源余额。
- AE 库存分页将本地可取/远端已知/预留/在途/不可达分开；有界持久调货、期限、取消与原生短缺异步补货复用独占划拨路径。新版本详情见 AE_NETWORK.md。
- 方块、物品、模型、原创材质、配方、双语 GUI；频道/设备/成员/邀请/加载/端点页，服务端参数和发送玩家授权、限流、玩家及管理员命令、健康/事务/配额/隔离诊断。

重要源码：`backend/Authority.java`、`Sql.java`、`Migrations.java`、`LocalJournal.java`、`RedisTransport.java`；`runtime/RuntimeService.java`、`ChunkTickets.java`；`block/TesseractBlockEntity.java`、`StackCodec.java`、`NeighborPump.java`、`Ports.java`；`network/Packets.java`、`client/TesseractScreen.java`；`compat/{gregtech,mekanism,ae2}`。它们均位于 `src/main/java/dev/crosstesseract/`。迁移位于 `src/main/resources/db/migration/`，资源位于 `assets/cross_tesseract/`。构建、配置和测试脚本位于项目根、`config/`、`deploy/`、`scripts/`。

## 实测结果与复现命令

以下时间均为 UTC；故障报告保留原始执行时间，没有冒称为最终绑定修复后的重新执行。

| 验证 | 实际结果 | 报告/主要日志 |
|---|---|---|
| 单元、性质、真实 MySQL/Redis 集成 | 27 个测试，失败 0、错误 0、跳过 0；性质运行 200/300 次 | `unit-tests.json`；`stock-final-build.log`；`build/test-results/test/` |
| 八种原生兼容组合，10-03 01:36 | 全通过；基础/Mek/AE/AE+Mek/GT/GT+Mek/AE+GT/三兼容必需测试数 7/9/10/12/9/11/12/14 | `compat-matrix.json`；`matrix-*.log`、`stock-final-matrix.log` |
| 三个独立 Minecraft JVM，10-03 02:12 | 物品/流体/FE 守恒、多发多收、跨服邀请、撤权及配额通过 | `three-server.json`；`stock-three-server-test.log` |
| AE 三 JVM，10-03 02:13 | B/C 原生缺货立即返回 0 并持久记录独立需求；24 钻石经 MEStorage→SQL/WAL→远端提取守恒；网格、多桥、失电、撤权代理通过 | `ae-three.json`；`stock-ae-three-test.log` |
| 票据恢复/Redis 故障，10-02 15:19 | 干净重启主动恢复；Redis 故障撤票但保留配额；SIGKILL 后新 epoch 隔离 | `recovery.json`；`final-recovery-test.log` |
| 四个实际 halt(97) 窗口，10-02 15:23 | 发送 WAL/提交、独占划拨、接收 WAL 后崩溃均保留阶段所有权；无盲目退款或重发 | `faults.json`；`final-fault-test.log` |
| MySQL 容器实际停启，10-02 14:14 | 实际票据归零、持久名额保留、新批准拒绝，游戏继续响应 | `mysql-outage.json`；`mysql-outage-test.log` |
| 官方 NeoForge 冷安装，10-03 02:35 | 最终相同 SHA 的 JAR 独立加载；无兼容模组，真实 1234 FE 跨缓冲交付、干净停止 | `packaged-smoke.json`；`stock-packaged-smoke-test.log`、`packaged-smoke.log` |
| 实际客户端，10-03 02:35 | Minecraft C2S 创建/绑定/配置及 AE 库存、调货、取消通过；32 钻石保持完整；英文及小窗口中文截图 | `stock-ui.json`、`screenshots/ui-stock-zh-remote.png`、`ui-stock-zh-pending.png`；`stock-ui-smoke.log` |
| 最终性能，10-03 02:26 开始 | 100/500/1000 真实端点完成，无设置/测量任务错误或队列拒绝 | `performance-final.json`、`raw/final.jfr`；`stock-final-performance-test.log` |

表内报告文件位于 `reports/`，日志位于 `logs/`。三 JVM 和性能冻结启动的传输/配额 class 与最终 class 一致；后续调整了库存页面的方向提示/按钮及客户端开发截图时机，逐文件对照见 `launch-class-parity.json`。未展示猜测数值或跳过测试。具体覆盖边界见 [TESTING.md](TESTING.md)。真实执行的主要命令：

```bash
scripts/test-matrix.sh
python3 scripts/three-server-test.py
python3 scripts/ae-three-test.py
python3 scripts/mysql-outage-test.py
python3 scripts/recovery-test.py
python3 scripts/fault-test.py
scripts/install-packaged-dev.sh --accept-eula
python3 scripts/packaged-smoke.py
scripts/ui-smoke-headless.sh -PtestMods=ae2
python3 scripts/performance-test.py --label final --seconds 20
```

### 区块加载并发结果

默认 `maxPerPlayer=2` 以群组权威政策为准。三 JVM 同时为同一玩家申请，最终恰好两份 ACTIVE 授权；A/B 各一份时 C 第三份被拒绝。成员设备计入成员配额，同区块两设备占两份名额，关闭其中一份仍保留另一份实际票据。Redis 失联/子服停机不会释放持久槽位；故障恢复不能靠心跳到期偷换新设备。

实际只请求设备所在区块的 ticking 票据；Minecraft 引擎可能连带加载其他区块。安装、恢复和区块加载有主线程成本，不能承诺物理上只驻留一个区块或零开销。远程关闭有 REVOKING 待确认状态；无法证明旧资格失效时不复用槽位。设计与操作见 [ARCHITECTURE.md](ARCHITECTURE.md)、[PLAYER_GUIDE.md](PLAYER_GUIDE.md)。

### 各兼容模块的实际状态

| 模块 | 已实现并实测 | 未完成/限制 |
|---|---|---|
| GT EU | FortyTwoCn 实际 IEnergyContainer、方向、电压/已接受安培、checked long 数量、真实 LV 能量仓；无默认 EU/FE 转换 | 使用披露的 MUI 替代闭包；未提供大整数扩展 |
| Mek 化学品 | 统一 IChemicalHandler、long、多槽、模拟、剩余量、SQL 到货；拒绝放射性/不支持属性 | 其他特殊属性/大型 modpack 未普遍验证 |
| Mek 热力 | 真实热接口、有限热容量、被动热量交换、守恒/残差/非法值处理、实际接口及性质测试 | 非逐 tick 本地热导管等价；高延迟稳定性和极端数值未完整压测，不能作反应堆唯一冷却 |
| AE Level 1 物资 | 真实 MEStorage、动作来源、本地独占到货额度、异步到货通知、同网网关去重、三 JVM 物资提取；五类库存状态分页及持久定向补货 | 复杂第三方别名环路未全面测试；FIFO 单种资源等待有六十秒边界 |
| AE Level 2 网络 | 默认关闭的真实 managed-node 实验代理，三 JVM 多端点/同网多桥/本地失电/撤权验证 | **原生网格、控制器、供电、安全和合成/请求服务跨 JVM 合并未完成** |

核心在缺少三种兼容模组时正常加载；八种顶层组合按真实必需依赖闭包构建，没有打包上游实现冒充前置。AE 两层分开报告，原型差异及技术缺口见 [AE_NETWORK.md](AE_NETWORK.md)。

### 性能结论的范围

单 Minecraft JVM、同加载 OFF 对照、四频道 FE 负载、本机 MySQL/Redis、每状态二十秒、无其他工厂机器。1000 个实际活跃端点：接收 138949.45 FE/s，模组 Runtime 主线程 p95 0.701483 ms、p99 1.096997 ms；不等于整服 MSPT，不代表容量上限。不同组件热点、多 JVM 大规模、工厂加载成本、网络延迟/丢包及长期容量未测。完整环境、100/500/1000 数字、优化前后原始 JFR 和指标语义见 [PERFORMANCE.md](PERFORMANCE.md)。

## 三子服启动与部署

开发环境显式接受 EULA 后：

```bash
scripts/install-jdk.sh
scripts/fetch-references.sh
scripts/dev-backends.sh
python3 scripts/setup-dev.py --accept-eula
scripts/gradle-dev.sh createServerALaunchScript createServerBLaunchScript createServerCLaunchScript
# 三个独立终端分别执行：
scripts/start-dev.sh A
scripts/start-dev.sh B
scripts/start-dev.sh C
```

游戏端口 25565/25566/25567；开发 RCON 25575/25576/25577；loopback MySQL 13306、Redis 16379。A/B/C 使用 `dev_three_v1` 和不同稳定 `server.id`。当前三个启动脚本为基础配置；现有测试世界包含 AE 等测试方块，复现可选组合时先按 TESTING.md 重新生成相应 profile，或使用独立新开发世界，不覆盖已有世界。world UUID 文件不可复制成另一台身份。

生产使用官方 NeoForge 安装环境和 JAR、外置凭据、可信服务端网络。不启动开发钩子，不暴露数据库给玩家，正确配置认证 UUID/可信代理转发。生产 TLS、代理在线身份转发和所有 GUI 页的专用服多玩家操作仍未实测；本环境 Mojang session/public-key 请求受网络限制。见 [DEPLOYMENT.md](DEPLOYMENT.md)。本次结束时测试 Minecraft JVM 已停止，本机隔离 Redis/MySQL 开发容器与数据保留。

## 数据完整性保证与剩余风险

MySQL 事务、outbox/inbox、独占划拨和自有 WAL 防止已知阶段的重复提交/领取，故障窗口实际注入。超时不退款；不明确外部动作进入隔离。`setChanged()` 不代表立即落盘，Redis ACK 不代表世界已保存。

**相邻原版箱子、第三方机器与 Minecraft 存档未加入该原子事务**：源抽取未存盘、目的接收未存盘以及单服独立回档都有不可判定窗口。非干净启动采取保守隔离和审计恢复，不能保证任意手工回档都被检测或不复制/不丢失。任意外部世界引用物品需要限制/专用适配，通用编解码并不自动使其安全。

群组一致备份、暂停/排空和恢复建议见 [RECOVERY.md](RECOVERY.md)。当前尚无完整元数据归档/一键群组恢复重基，含热残差封存资产不能自动回收；历史容量达到上限会产生背压。不能通过清理未决记录或盲目重发解除积压。其余未完成/未验证项以 [TASKS.md](TASKS.md) 为准，开发版不应被宣传为全部需求已验收的正式发行版。
