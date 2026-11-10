# 第三方组件与分发资料

本项目保留原项目文档中的 MIT 源码授权声明。第三方库由各自权利人授权，不能将运行包整体误称为全部仅受 MIT 授权。

| 组件 | 本次版本 | 授权与来源 |
|---|---|---|
| Python | 3.12.14 | Python Software Foundation；运行包 licenses/Python-LICENSE.txt |
| PySide6 / shiboken6 / Qt | 6.11.2 | Qt 官方 Python 绑定；开源使用条件含 LGPLv3，另有商业授权；见下方官方资料及随包许可证 |
| Qt WebEngine / Chromium | 随 Qt 6.11.2 | LGPL 与 Chromium 多项第三方授权；源资料与版权信息见官方页面及 licenses |
| MathJax | 3.2.2 | Apache-2.0；本地 assets/vendor/mathjax 下保留原始许可证 |
| marked | 12.0.2 | MIT；本地 assets/vendor/marked 下保留原始许可证 |
| DOMPurify | 3.2.6 | Apache-2.0 或 MPL-2.0；本地 assets/vendor/dompurify 下保留原始许可证 |
| openai Python SDK | 2.54.0 | Apache-2.0；随包 licenses/openai |
| keyring | 25.7.0 | MIT；随包 licenses/keyring |
| PyYAML | 6.0.3 | MIT；随包 licenses/PyYAML |
| PyInstaller | 6.22.3 | GPL 加引导程序分发例外；随包 licenses/pyinstaller |

完整 Python 依赖版本见 requirements-lock.txt；间接依赖的许可证也随包收集到 licenses。构建使用的固定渲染资源 URL 与 SHA256 见 assets/vendor/manifest.json。

## Qt 共享库与源代码

Qt / PySide6 共享运行库位于 _internal 中，可以用接口与版本兼容的修改版替换，不被加密绑定到应用。接收者可以为调试修改的 LGPL 组件而进行必要的逆向分析；本项目不施加禁止条款。

应用的完整可编辑源码与构建方式附在“数学知识织网-2.0.0-源码.zip”。Qt 与 PySide6 对应版本的上游源代码可从官方发布渠道取得，本项目没有修改 Qt、PySide6 或 Chromium：

- [Qt for Python 源代码发布目录](https://download.qt.io/official_releases/QtForPython/)
- [Qt 6.11 发布目录](https://download.qt.io/official_releases/qt/6.11/)
- [Qt for Python 许可证](https://doc.qt.io/qtforpython-6/licenses.html)
- [Qt WebEngine 许可证与第三方清单](https://doc.qt.io/qt-6/qtwebengine-licensing.html)
- [Chromium 开源许可证](https://chromium.googlesource.com/chromium/src/+/main/LICENSE)

随包 licenses 中另提供 LGPL 与 GPL 标准许可证文本，以及从当前 Qt WebEngine 导出的本地版本与版权信息页面。Chromium 组件的详细第三方清单可从上述 Qt WebEngine 官方授权页面取得。

## 图标

assets/app-icon.png 由本次任务使用内置 imagegen 生成；app.ico 由该图像转换而来。设计提示词为：深靛蓝圆角方形，以暖白积分符号和青色、淡紫色连接节点表达“数学知识织网”，简约、高对比、适合桌面小图标，无额外文字。

本说明提供随包组件、授权文件与来源入口；后续修改依赖或构建平台时，应同步重新收集对应组件资料。
