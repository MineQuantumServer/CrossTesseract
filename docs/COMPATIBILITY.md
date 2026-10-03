# 兼容版本和 API 调查

指定分支及完整 SHA 见 [THIRD_PARTY.md](THIRD_PARTY.md)。兼容源码独立在 `compat/gregtech`、`compat/mekanism`、`compat/ae2`；核心签名/父类/字段不引用可选模组类型，模块以类名字符串在 ModList 和配置开关确认后加载。缺依赖的 GameTest 类不自动扫描，只有已加载兼容模块登记。没有 Mixin，也没有把上游实现打包进本 JAR。

|模块|实际测试版本|运行前置闭包|状态|
|---|---|---|---|
|基础|Minecraft 1.21.1 / NeoForge 21.1.252|无 AE/MEK/GT|物品/流体/FE、频道、配额和原生能力实测|
|GT|FortyTwoCn 指定 SHA，gtceu 8.0.0|该源码 JAR 自带 ModularUI 3.3.1、Registrate、Configuration|真实 EU 能力及原生 LV 能量输入仓实测；MUI 预览依赖使用公开说明的本地替代|
|Mekanism|mekanism 10.7.19.85|Mekanism 主模组；Generators/Tools 非必需|化学品/长整数/放射性拒绝和热接口/被动交换实测|
|AE2 Level 1|ae2 19.2.18|GuideMe 21.1.1|本地独占库存、五类库存分页、持久调货/取消、原生短缺异步补货、SQL/WAL 到货实测|
|AE2 Level 2|同上|同上|实验代理节点；完整原生跨服网格目标未完成|

各模块支持 `-Dcross_tesseract.compat.gtceu=false`、`.mekanism=false`、`.ae2=false` 启动开关；关闭后不访问对应 API，也不删除数据库中已有资源。修改开关需重启。metadata 可选依赖声明区分未安装与版本不支持，使用固定验证范围，不宣称整个 1.21.x 全兼容。

## GregTech

直接调查目标 fork 的 `IEnergyContainer`、`IEnergyInfoProvider`、GT 能力注册、EnergyContainerHandler、能量仓机器定义及方向属性。能力 ID `gtceu:energy_container`。`acceptEnergyFromNetwork(side, voltage, amperage)` 返回接受的安培数，结算必须乘以原电压。输出到相邻仓使用真实能力缓存和该接口，不调用外部 `changeEnergy` 绕过电气规则。

每端默认 32V/1A，可配置同等级策略，profile 保存电压且 SQL demand 以电压为 packet quantum。错误电压拒绝，不自动变压；每 tick 安培和容量限制，剩余 EU 保留。EU 和 FE 不兑换。输入/输出方向及原生仓前面朝向在 GameTests 中实际设置/验证。接口传输数量为 long，`IEnergyInfoProvider` 的 BigInteger 能量显示不意味着已支持任意大整数传输；超过 long 的扩展未实现。

目标 SHA 的原始公开 Maven 构建报错：`brachy.modularui:modularui-mc1.21.1:3.3.1-jei19.57-preview1` 不可解析（`logs/gt-build.log`）。采用以下可复现、明确标识的源码依赖变体；未修改两个参考仓库源码或伪造 preview1 版本：

```bash
scripts/fetch-references.sh --with-gt-runtime
scripts/build-reference.sh modularui-modern \
  -I /workspace/scripts/reference-maven-mirror.init.gradle build publishToMavenLocal
scripts/build-reference.sh gregtech \
  -I /workspace/scripts/reference-maven-mirror.init.gradle \
  -I /workspace/scripts/gt-local-mui.init.gradle build
scripts/gradle-dev.sh runGameTestServer -PgameTestBackend -PtestMods=gregtech
```

工作区不在 `/workspace` 时把 init script 参数换成当前仓库绝对路径。MUI 源码 SHA `8ecb104d0c38b1eb9baab5c837624034db7ca873` 产出 3.3.1，日志 `mui-build.log` / `gt-local-build.log`。此变体已构建及实测；不可宣称原始缺失 preview1 artifact 已测试。发布或运营使用需明确选择该源构建及许可，保留 fork commit 与替代记录。

## Mekanism

调查统一 `IChemicalHandler`、`ChemicalStack.CODEC`、Chemical 属性验证和辐射属性，未使用旧 gas/fluid 接口。插入返回未插入的 remainder，模拟和执行均不修改调用方栈，多槽和 long 数量部分接收。包含 Radioactivity 或不能按当前 attribute validator 处理的类别拒绝输入，不利用跨服消除放射性风险。注册表不存在时不可交付，基础资源不受该类别阻塞。

热接口使用 `IHeatHandler` / `IHeatCapacitor` 语义，定义有限 10000 J/K 的本地/频道热容模型，热量以微焦耳结算而非复制温度。被动交换仅从热端到冷端，单步限制不会超过平衡温度；扣热/加热和残差对应。模型不模拟原生热管逐 tick 网络延迟；断网暂停，不能作为高风险反应堆唯一安全冷却保障。热容/传导参数非法、NaN、Infinity 拒绝。

## AE2

调查 `MEStorage`、`IStorageProvider`/`IStorageMounts`、`IActionSource`/`IActionHost`、`IManagedGridNode`/`IGridNode`、GridHelper、存储缓存通知、IPathingService、ControllerState、IEnergyService、ICraftingService、CraftingService 和 CPU/request 路径。此指定分支未提供旧版本 `ISecurityService`/`SecurityPermissions` API；只存在 action source/host、玩家映射和相关 ownership 逻辑。没有按旧版本记忆虚构安全接口。

Level 1 每设备一个实际 in-world managed node/provider，拥有玩家映射，消耗本地 AE 电力/频道。库存只有持久独占 RX，远端未知余额不会被同步 extract 当作可取。原生 item/fluid handler 在 AE 模式下关闭，且不再暴露 ME_STORAGE 第二挂载入口，降低存储总线/子网别名重复统计。simulate、partial、来源及本模组权限检查，增量脏标记触发 AE 缓存失效，不完整扫描远端网络。

玩家来源采取设备主人匹配的保守限制，机器来源依据有效绑定；这比把任意频道成员的玩家动作都放行更严格。原生 crafting 和 request 服务跨服代理未实现，详细层级区别/验证矩阵见 [AE_NETWORK.md](AE_NETWORK.md)。
