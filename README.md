# CrossServer Tesseract · 跨服超立方体

Minecraft **1.21.1 / NeoForge 21.1.252 / Java 21** 开发模组。独立子服通过同一 MySQL 群组共享私有资源频道，Redis 负责提示和在线状态。客户端只连接自己的 Minecraft 服务端。

这是 **0.1.0-dev 开发交付**。基础传输、全群组加载配额、GT EU、Mekanism 化学品/热力以及 AE2 物资网关已有真实实现和测试。**AE2 原生跨 JVM 网络合并尚未完成**；独立的实验原型使用真实 AE 节点进行代理频道消耗，不能替代原生网络合并。见 [AE 两个层级与技术缺口](docs/AE_NETWORK.md)。没有发布正式发行版。

## 构建

使用已安装的 Java 21，或执行固定版本 JDK 安装脚本。参考仓库保持只读，GT 的两个 compile-only 接口直接从指定 SHA 编译，不会进入本模组 JAR。

```bash
scripts/install-jdk.sh
scripts/fetch-references.sh
scripts/gradle-dev.sh build
```

产物：`build/libs/cross_tesseract-0.1.0-dev.jar`，以及同目录 sources JAR。Minecraft、NeoForge、AE2、Mekanism、GT 均不被打包；MySQL/Redis 客户端等固定版本库通过 Jar-in-Jar 嵌入。Gradle wrapper、插件版本和各兼容组合依赖锁已固定。普通 `build` 不启动数据库，真实后端测试需额外指定下述开关；被跳过的集成测试不算通过。

## 三子服开发环境

这些命令只用于本机隔离测试，端口及测试凭据见脚本。先阅读并接受 Minecraft EULA，再使用 `--accept-eula`。生产部署见 [部署与身份](docs/DEPLOYMENT.md)。

```bash
scripts/dev-backends.sh
python3 scripts/setup-dev.py --accept-eula
scripts/gradle-dev.sh test -Dct.integration=true \
  createServerALaunchScript createServerBLaunchScript createServerCLaunchScript
```

在三个独立终端中分别启动：

```bash
scripts/start-dev.sh A
scripts/start-dev.sh B
scripts/start-dev.sh C
```

A/B/C 的游戏端口为 25565/25566/25567，测试 RCON 为 25575/25576/25577。三台使用 `dev_three_v1` 群组及不同稳定 `server.id`；世界 UUID 自动保存在各世界目录。不要把任何一台的世界身份文件复制到另一台。

```bash
python3 scripts/three-server-test.py
python3 scripts/recovery-test.py
python3 scripts/fault-test.py
scripts/test-matrix.sh
```

后两项故障脚本会停止测试 Redis 或强制终止指定开发 Minecraft JVM，不能用于运营服。测试钩子只有显式启用 `cross_tesseract.testHarness` 且群组以 `dev_`/`test_` 开头时才可用。

## 玩家使用

合成、放置超立方体，右键打开配置界面；放置玩家的服务端 UUID 是设备主人。创建频道，邀请其他玩家 UUID，由对方接受后绑定其自己的设备。频道默认私有，知道频道编号不授予权限。

在“设备”页为物品、流体、FE 设置发送/接收/双向、侧面和速率；发送与接收缓冲独立，双向不会自动把接收库存重新发送。安装兼容模组后显示对应资源项。频道管理、邀请、成员、加载配额和端点都有独立页面；异步操作显示处理中及最终结果。支持 `en_us`、`zh_cn`。

基础资源可直接与相邻能力容器交换：SEND 有界轮询抽入，RECEIVE/BOTH 输出已到货额度。BOTH 接收上游管道输入，但不自动抽回相邻输出容器，避免同一容器中的网络到货无限循环；需要双向自动布局时使用分开的发送端与接收端。每次只访问一个侧面和槽位，缓存按真实能力失效通知刷新。

AE2 安装并开启物资桥后增加库存页，区分本地立即可取、远端已知、预留、在途和不可达。选择资源及数量可异步调货，取消仅撤销未分配需求；原生 AE 实际提取不足也会有界请求短缺，模拟没有副作用。远端数量不作为同步可提取额度。

加载默认每玩家全群组合计 **2 个设备**，计入设备主人。相同区块内两个设备仍占两个名额；关闭其中一个不撤销另一个的票据。离线及子服停止不释放持久配额。见 [频道与配额操作](docs/PLAYER_GUIDE.md)。

## 维护与证据

- [最终交付、构建产物、实测结果与缺口](docs/DELIVERY.md)
- [实施清单与未完成项](docs/TASKS.md)
- [数据模型、线程和传输状态机](docs/ARCHITECTURE.md)
- [崩溃边界、隔离恢复、备份与回档](docs/RECOVERY.md)
- [具体兼容版本与来源](docs/COMPATIBILITY.md)、[第三方许可](docs/THIRD_PARTY.md)
- [测试命令、覆盖范围和结果](docs/TESTING.md)、[性能实测与调参](docs/PERFORMANCE.md)
- [管理员诊断与恢复命令](docs/OPERATIONS.md)

`reports/` 保存实际三服、崩溃恢复、兼容矩阵及性能报告；完整控制台日志位于 `logs/`，JUnit XML 位于 `build/test-results/test/`。报告区分真实实测、实验原型和未验证项目。资源守恒覆盖本模组 WAL 与 SQL 所有权阶段；**第三方机器、原版箱子和独立回档并未加入同一个原子事务**。不宣称任意崩溃和任意回档下绝对不复制或不丢失。

本项目原创代码/材质为 MIT。原始 Tesseract 为受限许可参考，不包含其代码、PNG、模型或改色资源。
