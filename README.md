# 数学知识织网 · MathWeave

把数学对话整理成带公式、双向链接和知识地图的 Obsidian 笔记。它是独立的 Windows 桌面程序，不是 Obsidian 插件。

[下载 Windows 版](https://github.com/Li-FengChen/mathweave-obsidian/releases) · [使用教程](docs/使用说明.md) · [提交反馈](https://github.com/Li-FengChen/mathweave-obsidian/issues/new/choose)

![程序图标](assets/app-icon.png)

## 快速开始

1. 在 [Releases](https://github.com/Li-FengChen/mathweave-obsidian/releases) 中下载带 **Windows-x64.zip** 的附件，不要下载页面自动生成的 **Source code** 压缩包来运行程序。若暂时没有附件，可按下文从源码运行。
2. 将压缩包完整解压，双击 **数学知识织网.exe**。不要单独移动 `.exe`，它需要同目录的 `_internal` 文件夹。支持 Windows 10/11 x64，无需安装 Python。
3. 点击 **体验示例**，无需密钥即可查看公式、示例笔记和知识关系。
4. 在 **设置** 中选择 Obsidian 仓库和 AI 服务，粘贴对话或导入 `.txt`、`.md`、`.json` 文件，再提取、校对并保存。首次使用建议选一个测试仓库。

## 功能与注意事项

- 生成定义、定理、折叠证明、例题等卡片，使用本地 MathJax 渲染公式。
- 在保存前编辑笔记和知识关系；保存时生成双向链接、知识地图和索引。
- 默认将每次导入独立保存；勾选 **更新已有笔记** 后才会补充同名笔记。
- **AI 整理笔记库**可识别重复概念并补充关系。打开图形整理窗口会自动开始；如需在任何写入前核对方案，请使用命令行 `--maintain --preview`。写入时保留快照，撤销不会覆盖后续手动编辑。
- 使用 AI 提取或整理时，相关对话或笔记会发送给你配置的服务。内置示例、公式预览和本地提取不调用 AI。保存前请核对数学结论，不要提交私密对话或 API 密钥反馈问题。

## 从源码运行

以下命令适用于 Windows 和 Python 3.12。从 [仓库首页](https://github.com/Li-FengChen/mathweave-obsidian) 克隆项目或下载源码，进入源码根目录后运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe main.py --demo
```

公式预览所需资源已包含在源码中；去掉 `--demo` 即可正常启动。无界面的本地导入示例：

```powershell
.\.venv\Scripts\python.exe main.py --cli --no-ai --file .\input.md --vault "D:\MyVault"
```

使用 `main.py --help` 查看全部参数。运行测试、构建便携包和发布版本的步骤见 [贡献指南](CONTRIBUTING.md) 和 [分享与打包](docs/分享与打包.md)。macOS 和 Linux 目前不提供经过验证的运行包。

## 项目资料

- [使用教程](docs/使用说明.md) · [数学笔记格式](docs/数学笔记格式与依据.md) · [版本记录](CHANGELOG.md)
- [Windows 自动检查](https://github.com/Li-FengChen/mathweave-obsidian/actions/workflows/check.yml) · [贡献指南](CONTRIBUTING.md) · [安全问题报告](SECURITY.md)
- 项目源码采用 [MIT 许可](LICENSE)；运行包包含遵循各自许可证的 [第三方组件](THIRD_PARTY_NOTICES.md)。
