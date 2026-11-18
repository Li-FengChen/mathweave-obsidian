# 贡献指南

## 报告问题

先搜索 [现有问题](https://github.com/Li-FengChen/mathweave-obsidian/issues)，再用相应模板说明版本、操作步骤与预期结果。公式或导入问题请尽量附一段能单独复现的虚构示例，不要提交私人笔记、API 密钥或未经脱敏的日志。安全问题请看 [安全报告方式](SECURITY.md)。

## 开发与验证

按 [README](README.md#从源码运行) 准备 Windows x64 / Python 3.12 环境。在单独的分支上提交聚焦的修改，并在拉取请求（PR）中说明改动和验证结果。涉及笔记写入、备份或撤销时，请用临时 Obsidian 仓库测试。

```powershell
$env:MATH_OBSIDIAN_HOME = Join-Path $PWD '.qa\dev-state'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\qa_gui.py
```

这两项检查不需要真实 AI 密钥。涉及界面改动时，可补充有帮助的截图；涉及用户操作的改动请同步更新 [使用说明](docs/使用说明.md)。

## 构建与发布

1. 将 `core/resources.py` 中的 `APP_VERSION` 与 [版本记录](CHANGELOG.md) 更新为要发布的版本。
2. 在 Windows x64 上运行 `pwsh -File .\build_windows.ps1`，确认打包检查通过；新环境请先让 `python --version` 指向 Python 3.12。
3. 维护者确认目标代码已进入 `main` 且 Windows 检查通过后，推送与 `APP_VERSION` 一致的版本标签，例如 `v2.2.1`。不要重复使用已发布的标签。
4. [Windows release](https://github.com/Li-FengChen/mathweave-obsidian/actions/workflows/release.yml) 会验证标签、重新构建，并发布 Windows 包、源码包和 SHA-256 校验值。发布后确认三项附件均可下载。

详见 [分享与打包](docs/分享与打包.md)。不要把 `dist/`、`release/`、测试仓库或任何个人配置提交到 Git 历史。
