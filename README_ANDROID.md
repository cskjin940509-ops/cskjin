# A股筛选池：Android + Windows

两个客户端直接编译 `app/src/main/java/com/rui/astockstrategy/v6` 中的同一套页面和数据访问代码。功能包括总览、市场、机会、组合、研究、股票/板块详情、交易计划、手工账本、底仓 T、冻结证据和历史回放。

Android 的系统入口、SQLite、偏好存储与剪贴板适配在 `app/src/main/java/com/rui/astockstrategy/platform`；Windows 的窗口、本地存储与剪贴板适配在 `desktop/src/main/kotlin`。Windows 数据保存在 `%LOCALAPPDATA%/AStockResearch/Data`，与安装目录分开；程序使用单实例文件锁避免多窗口同时修改手工账本。缓存与偏好文件采用临时文件加原子替换。

后台研究结果两端共用；手工账本按设备独立保存，可用“复制备份/导入备份”交换。客户端不会发送券商真实订单。

## 同步更新约定

1. 修改公共页面与逻辑，避免另建 Windows 页面副本。
2. 在 `version.properties` 同时递增 versionName 和 versionCode，并更新 RELEASE_NOTES.md。
3. 将变更合并到 `codex/v4-latest-framework`。`Build Android and Windows together` 并行编译两个安装包；先通过共享代码检查和13项云端契约检查。
4. Windows 通过打包运行环境、本机存储重开、缓存与日志备份自检，并成功打开真实窗口生成截图后，两端安装包才能进入统一 Release。
5. 发布任务验证两个包的代码提交一致，上传全部资产后才公开，附 SHA256SUMS.txt。任一端失败不会发布另一端。顶部“更新”打开统一下载页，不静默安装。

## 构建

- Android：JDK17、Android SDK36、Gradle8.13，运行 `gradle :app:assembleDebug`。
- Windows：Windows x64、JDK17、WiX3.14、Gradle8.13，运行 `gradle -PdesktopOnly=true :desktop:packageExe`。EXE内置运行环境，终端用户无需安装Java。
- Windows入口仅共享客户端功能，不把后台策略迁到个人电脑；后台时效限制不会因为安装EXE而消失。

研究版 Android 签名密钥通过固定 Actions cache 复用；发布时对比上一个双平台版本的签名。缓存丢失或密钥变化时拒绝发布新版本，避免生成无法覆盖安装的更新。生产化发行应将签名密钥迁入维护者管理的持久秘密存储。v4.6及以前流水线未持久保留签名，首次迁移可能需导出本机账本后卸载旧包。
