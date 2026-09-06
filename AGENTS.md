# A股筛选池客户端维护约定

- 用户要求 Windows EXE 与 Android APK 功能一致、以后同步更新。
- `app/src/main/java/com/rui/astockstrategy/v6` 是两端直接编译的公共界面和数据逻辑。不要复制出独立桌面业务页面。
- 平台差异放在 Android `platform` 或 `desktop` 的适配层；保持手工账本导入导出 schema 兼容。
- 发布时只通过 `version.properties` 统一修改版本号和 Android versionCode，并更新 RELEASE_NOTES.md。
- 使用 `Build Android and Windows together` 验证两端；两个安装包都成功且来源提交一致，才能发布统一 Release。不要只交付一个平台而宣称同步更新已完成。
- Windows 打包后检查实际启动、五个主页面截图、本机账本/缓存重开；Android 保留应用ID和持久数据名称。不能把缺失证据默认成通过。
- Android 签名必须保持可升级。签名校验失败时修复密钥来源，不能删除签名一致性校验来强行发布。
