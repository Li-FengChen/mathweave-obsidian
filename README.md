# 数学知识织网 · 2.2.1

把数学对话整理成相互连接的 Obsidian 笔记。

![程序图标](assets/app-icon.png)

## 直接使用

双击项目里的“数学知识织网”快捷方式，或解压 release 中的 **数学知识织网-2.2.1-Windows.zip**，双击 **数学知识织网.exe**。无需安装 Python，也无需安装 Obsidian 插件。

第一次可以点击 **体验示例**：无需密钥即可查看公式、阅读四篇示例笔记，并浏览它们的知识联系。

正式使用时点击 **设置**，选择自己的 Obsidian 仓库和 AI 服务。粘贴或导入对话，分析后编辑、勾选笔记，选择是否勾选 **更新已有笔记**，再点击 **保存到 Obsidian**。

## 这次更新

- 设置自动载入已存 API 密钥，提供“显示／隐藏”和“删除”。默认隐藏，删除在保存后生效，取消则保留；各服务商的密钥分别管理。

- 每次保存可勾选“更新已有笔记”：默认不勾选，独立保存；勾选后补充同名笔记并按设置核对新旧联系。

- 保存完成后，窗口中央显示“保存成功”和实际保存数量，约 3 秒后自动消失。

- **AI 整理笔记库**：默认扫描数学笔记子目录，核对重复概念，用完整正文二次确认后整合，补充已有笔记之间的双向联系。
- 新笔记保存时核对与已有数学笔记的联系，统一实际目标路径并补上反向关系。
- 定义框、定理框、默认折叠的证明、例题与适用条件；预览支持原生及嵌套 Callout。
- 整理记录、全部变更、整理后笔记预览、可选“仅生成方案”与“撤销最近一次整理”。
- 合并保留完整原文、人工备注与事务快照；旧文件保留跳转，便于已有链接继续访问。
- 长对话分段与跨段关系核对，消息来源位置与待核对状态。
- 保存差异预览、批次写入恢复、进程锁、编辑冲突检查、递归索引与配置校验。
- JSON 参数自动兼容，仅重试临时错误；任务取消与窗口退出安全处理。
- 保留知识点之间的依赖、推广、应用、特例、等价与对比；生成双向 wikilinks 和关系说明。
- 不同概念保持独立，不再仅凭标题包含关系误合并。
- 每次保存额外生成一篇对话知识地图，保存本次讨论的整体联系。
- 三栏窗口：对话素材、知识点、阅读与校对。支持勾选保存与编辑标题、分类、标签、正文和知识联系。
- 离线 Markdown + MathJax 预览，支持矩阵、分段函数、多行对齐、常见宏与多种公式分隔符。
- 保留已有笔记与人工内容，完整追加补充块；重复结果跳过，更新前可备份。
- 修复导入角色、JSON 分支、空时间、分类索引自引用及文件名冲突。
- 新图标、内置教学示例、应用内使用教程、便携程序与源码分享包。

## 教程与分享

- [使用说明](docs/使用说明.md)：首次配置、日常操作、知识关系、公式语法与常见问题。
- [分享与打包](docs/分享与打包.md)：如何给朋友发送程序、如何更新、如何重新打包。
- [数学笔记格式](docs/数学笔记格式与依据.md)：模板与公开参考来源。
- [优化完成情况](docs/2.1优化完成情况.md)：最初 20 项问题的改动与验证结果。
- [第三方授权说明](THIRD_PARTY_NOTICES.md)：运行库、来源和分发注意事项。

发送 release 中的 Windows.zip，接收者解压整个文件夹后运行。不要只发送 exe；接收者需要配置自己的密钥和仓库。

## 源码运行

使用 Python 3.10 或更新版本。推荐创建虚拟环境：

    py -3.12 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements-lock.txt
    .venv\Scripts\python.exe tools\fetch_assets.py
    .venv\Scripts\python.exe main.py

教学示例：

    .venv\Scripts\python.exe main.py --demo

命令行（默认独立保存，添加 --update-existing 才允许更新旧笔记）：

    .venv\Scripts\python.exe main.py --cli --file conversation.json --vault "D:\MyVault"
    .venv\Scripts\python.exe main.py --cli --no-ai --file input.md --vault "D:\MyVault"
    .venv\Scripts\python.exe main.py --cli --update-existing --file input.md --vault "D:\MyVault"
    .venv\Scripts\python.exe main.py --cli --maintain --scope math --vault "D:\MyVault"
    .venv\Scripts\python.exe main.py --cli --maintain --preview --vault "D:\MyVault"
    .venv\Scripts\python.exe main.py --cli --undo-maintenance --vault "D:\MyVault"

Windows 程序包构建：运行 build_windows.ps1。requirements-lock.txt 记录本次已验证环境的依赖版本。

GUI 改用 Qt 官方 Python 绑定 PySide6。运行包包含本地渲染资源及共享运行库，不读取开发电脑上的虚拟环境。

## 验证

    .venv\Scripts\python.exe -m unittest discover -s tests -v
    .venv\Scripts\python.exe tools\qa_gui.py

核心检查使用临时仓库，不连接真实 AI。GUI 检查覆盖真实本地公式渲染、Markdown 分隔线、自定义宏和脚本过滤。

49 项回归检查、嵌套框折叠、整理与撤销流程已验证，密钥检查只使用测试密钥。已配置的 DeepSeek 服务另用 5 个公开提取样例和一个临时库整理样例检查；这些小样例不代表任意笔记库的准确率。公开样例在 tests/fixtures，可以显式执行以下命令复查：

    .venv\Scripts\python.exe tools\evaluate_math.py --live

此评估只发送公开样例，不读取实际笔记库。整理后的内容仍须核对数学条件。大库采用分段和候选检索，可能漏掉隐含关系；不确定的合并保留独立笔记。

AI 整理始终保留备份。若整理后又人工编辑，自动撤销会停止，避免覆盖后续内容；原内容仍在 .agent_backup 中。源码采用 [MIT](LICENSE)，第三方组件遵循其随包许可证。

## 目录

- core/：对话解析、知识关联、笔记与地图保存。
- ai/：服务客户端和提取提示词。
- ui/：窗口、主题与离线预览。
- assets/：图标、预览页面和固定版本的渲染资源。
- tools/：资源准备、实际界面检查与分享包生成。
- tests/：内容完整性和知识关联的回归检查。
- release/：可双击运行的 Windows 文件夹、分享压缩包和源码压缩包。

当前便携包面向 Windows 10/11 x64。本次在 Windows 11 上验证；macOS、Linux 需要在对应系统重新构建。
