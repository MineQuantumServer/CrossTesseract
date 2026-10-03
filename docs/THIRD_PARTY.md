# 参考来源与许可

调查日期：2026-10-02。参考仓库位于开发用 scratch/upstream，均保持只读。

|来源|指定分支|调查 SHA|版本/ID|授权与用途|
|---|---|---|---|---|
|AppliedEnergistics/Applied-Energistics-2|1.21.1|db17504a86128fdf3dae31f5fb7a112a646e0b93|ae2；NeoForge >=21.1.169|主体 LGPL-3.0；多数 API MIT，AECapabilities 等以各文件头为准；读取 API，不复制实现/资源|
|FortyTwoCn/GregTech-Modern|1.21|c72dc16b52795cbb0456b6e15e13cc4a85c0ed1b|gtceu 8.0.0（分支源码）|LGPL-3.0；以此 fork 为实际目标，不替换上游|
|mekanism/Mekanism|1.21.x|bcd7a8bf594cff9614eb12238fe3776f19da24d9|mekanism 10.7.19（构建号另计）|MIT；调查化学品、热力、序列化接口|
|SuperMartijn642/Tesseract|neoforge-1.21|cedf6df38a02d1f204733f2d8723d7f99861d972|tesseract 1.0.38|gradle.properties: All rights reserved；只参考交互组织、视觉语言；不打包其代码/材质/模型|
|NeoForgeMDKs/MDK-1.21.1-ModDevGradle|main|7819b902a351b03fe71db00754d103b5a31c4ebf|NeoForge 21.1.252 / ModDevGradle 2.0.148 / Gradle 9.2.1|MDK 构建工具参考；Gradle wrapper 是构建工具，Apache-2.0|

本项目原创源码与资源使用 MIT（见根目录 LICENSE）；不存在将受限上游资源简单改色再分发的授权假设。

随 JAR 嵌入的库：HikariCP 6.2.1 (Apache-2.0)、Connector/J 9.2.0 (GPL-2.0 with Universal FOSS Exception)、Jedis 5.2.0 (MIT)、commons-pool2 2.12.0 (Apache-2.0)、JSON-java 20240303 (public domain)。Minecraft/NeoForge 和可选模组不合并进本模组 JAR。本项目 MIT 许可属于 Connector/J Universal FOSS Exception 列出的许可。嵌入库保持独立 JAR，保留其原有许可与声明；源码获取地址及许可说明另见打包的 META-INF/THIRD-PARTY-NOTICES.txt。当前 0.1.0-dev 为开发交付，未发布正式发行版。

本地 GT 可运行构建：指定 fork/commit 不变。其 `3.3.1-jei19.57-preview1` ModularUI 依赖公开 Maven 不可取得；使用 `brachy84/ModularUI-Modern` 的 `1.21.1` 分支 SHA `8ecb104d0c38b1eb9baab5c837624034db7ca873`，原版 3.3.1 本地构建/安装，并通过本仓库外置 init script 明示替代依赖（未伪装成 preview1，也未修改参考源码）。两仓库 `git status --porcelain` 保持空。GT JAR 内含其自己的 LGPL ModularUI、Registrate 和 Configuration 前置；它们不嵌入本项目的 JAR。

官方 NeoForge 文档实际读取 `neoforged/Documentation` SHA `89528c36e4eb34d46b1de346c045172ce8ca9fde` 中的 `versioned_docs/version-1.21.1`；原 URL 返回 404 时使用版本化源码。
