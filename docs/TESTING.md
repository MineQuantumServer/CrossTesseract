# 实际测试与复现

测试只连接脚本建立的本机 `cross_tesseract` 开发数据库和 Redis。执行前接受 EULA，阅读各故障脚本说明。结果以 `reports/*.json`、完整 `logs/` 和 JUnit XML 为依据；测试规模不等于容量承诺。

```bash
scripts/install-jdk.sh
scripts/fetch-references.sh --with-gt-runtime
scripts/dev-backends.sh
python3 scripts/setup-dev.py --accept-eula
scripts/gradle-dev.sh test -Dct.integration=true
# 首次 GT 原生测试先按 COMPATIBILITY.md 构建完整 GT/MUI runtime。
scripts/test-matrix.sh
```

普通 `test` 会跳过需要后端的测试；本次验收实际使用 `-Dct.integration=true`，没有用 H2 替代 MySQL，也没有以内存 Redis 计算资产。单位及性质测试覆盖缓冲模拟/执行、部分领取、重复凭证、Long 溢出、200/300 次随机热/资源性质检查、载荷与 WAL 损坏、AE 代理规划。真实后端覆盖邀请并发接受、唯一主人、配额竞争、幂等余额、超过 2^53 的整数、SQL 死锁重试、outbox 未发布提交、Redis pending/消费者重启/重复和乱序、并发迁移及中断 DDL、隔离凭证恢复和历史容量。

`test-matrix.sh` 顺序启动八个真实 NeoForge GameTest JVM：基础、Mek、AE、Mek+AE、GT、GT+Mek、GT+AE、三兼容同时存在。每次都有真实 MySQL/Redis，模组缺失组合不解析对应运行类。GT 是指定 FortyTwoCn 源码构建，缺失 ModularUI preview 使用明确记录的 3.3.1 替代闭包；见 [兼容版本](COMPATIBILITY.md)。脚本读取原生 GameTest 成功数和 Gradle 退出状态写报告，失败不算通过。

原生游戏测试覆盖完整 ItemStack/FluidStack 组件、无效注册表/超大嵌套载荷拒绝、方向与 simulate、真实 vanilla chest 多槽部分接收、能力缓存失效、GT 实际能量仓与电压/安培、Mek 化学品 long/剩余量/放射性拒绝及热量、AE 真实 MEStorage 和 managed nodes 的频道不足/恢复。它们没有证明所有第三方管道、可移动机器和外部存储引用都兼容。

库存补齐后的单元/真实后端测试共 27 个，新增指定资源需求、幂等重复、独占预留与取消不退款、无权限资源元数据拒绝、8+2 行分页、八请求上限、期限与绑定切换。AE 原生测试增加真实模拟零副作用、本地短缺立即返回、持久请求及完整组件指定到货。命令 `scripts/gradle-dev.sh test -Dct.integration=true runGameTestServer -PgameTestBackend -PtestMods=ae2`；日志 `logs/stock-ae-tests.log`。

## 三个独立服务器

按 README 建立并启动 A/B/C 后：

```bash
python3 scripts/three-server-test.py
python3 scripts/mysql-outage-test.py
python3 scripts/recovery-test.py
python3 scripts/fault-test.py
```

三服测试通过控制台隔离 fixture 行为调用真实服务端能力与数据库：A 建频道、B 邀请、C 接受；A→B/C 物品/流体/FE 守恒，A/B→C 多发送；三服同时申请同一玩家配额最终恰好两个；同区块两设备关闭其一不影响另一票据；成员自己的配额与移除后的有界撤权。控制台 fixture 的 UUID 不是在线玩家认证测试，本项目没有将它冒称为真实代理转发联调。

MySQL 故障实际停止容器并重启，验证票据撤销、持久名额保留、新批准拒绝以及 Minecraft 命令响应。Redis 故障实际停止服务、重启并 FLUSHDB，仅影响可恢复提示，不删除 SQL 资产。恢复测试正常停止/重启真实 Minecraft，再 SIGKILL；故障注入在四个 WAL/SQL 阶段 `halt(97)`，确认新 epoch 隔离、不超时退款、不重复再发。运行这些脚本期间不要并行操作同一测试服务器或后端故障。

## AE 两层分别验证

Level 1 的原生存储测试位于 AE GameTest；Level 2 本地真实节点/规划器测试单独执行，不能合称“原生网络已合并”。三服实验代理测试使用：

```bash
scripts/gradle-dev.sh createServerALaunchScript -PtestMods=ae2,mekanism -PaePrototype
scripts/gradle-dev.sh createServerBLaunchScript -PtestMods=ae2 -PaePrototype
scripts/gradle-dev.sh createServerCLaunchScript -PtestMods=ae2,gregtech -PaePrototype
# 分别在三个终端启动 A/B/C，再执行：
python3 scripts/ae-three-test.py
```

该测试查询真实 grid UUID/频道消费者；B/C 原生缺货立即返回零并记录两份持久需求，然后跨 JVM 插入/提取二十四个钻石，并检查同网多桥、失电及撤权。报告 `ae-three.json` 仅证明报告中列出的实验语义；控制器/安全/电力/合成服务的原生合并尚未完成。

## 客户端与独立安装包

实际 Xvfb 客户端打开本模组 GUI，通过 Minecraft C2S 包创建/绑定频道及设置 FE，保存英文和小窗口中文截图，见 `reports/screenshots/`、`logs/stock-ui-smoke.log`。复现：安装 Xvfb 后运行 `scripts/ui-smoke-headless.sh`，它分配独立显示会话并正常清理；也可自行设置 DISPLAY 后运行 `scripts/gradle-dev.sh runClientSmoke`。测试使用真实 integrated ServerPlayer；真实在线专用服 GUI、所有管理页操作和全部窗口尺寸仍未逐项实测。

安装真实 AE 的库存 GUI 扩展测试使用 `scripts/ui-smoke-headless.sh -PtestMods=ae2`：原生 AE 实际插入 32 钻石，SEND 模式显示远端 32/本地 0；RECEIVE 到货显示本地 32，C2S 调货 1 个形成未分配需求，C2S 取消后本地 32 保持。扩展通过以 `CT_UI_STOCK_PASS`、Gradle 成功和 `reports/stock-ui.json` 为准，截图分别记录远端观测及待分配状态。

重复测试使用新空坐标，保留上轮世界/封存资源。开发过程中 `stock-ui-registration-failed.log`、`stock-ui-sealed-location-debug.log` 保留旧固定位置受封存阻止的失败；`stock-ui-assisted-debug.log` 为有人工点击诊断的一轮，不能算无人干预通过。`stock-ui-teleport-debug.log`、`stock-ui-ground-height-debug.log`、`stock-ui-heightmap-debug.log` 保存空坐标布置/未加载高度图的测试失败；已按实际 1.21.1 Level/Chunk 源码预生成测试区块后读取高度，等待客户端位置/区块确认，并限制总测试时长及重生次数。最终库存测试只有 `stock-ui-smoke.log` 且两种 PASS 标记/正常退出同时存在才计为通过。界面绑定在服务器确认 registered 前停用。截图复核发现第一轮远端截图抓取早于渲染，保留为 `stock-ui-pre-render-delay.log` / `ui-stock-zh-remote-pre-render-delay.png`；最终开发 hook 等待八个客户端 tick 渲染后再抓取，避免将上一帧加载状态作为库存证据。

独立包测试使用官方 NeoForge installer 的冷安装目录，直接 `run.sh --nogui` 加载最终 Jar-in-Jar 产物，不依赖 Gradle 开发 classpath。独立安装报告及构建清单另保存在 `reports/`。

```bash
scripts/gradle-dev.sh build -Dct.integration=true
scripts/install-packaged-dev.sh --accept-eula
python3 scripts/packaged-smoke.py
```

## 未验证边界

任意外部容器保存回退不具原子保证；生产 TLS/可信代理认证、所有大型 modpack、网络高延迟/丢包、1000 端点多 JVM 热点物品组件及完整 AE crafting 恢复未验证。性能脚本与指标含义见 [性能报告](PERFORMANCE.md)。不要把短测试外推为长期生产完整性或吞吐承诺。
