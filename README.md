# 小钻风音频切换器 v1.0

Windows 音频输出设备一键切换工具 —— 系统托盘常驻、全局热键支持、操作极简。

## ✨ 功能

- **一键切换** — 双击设备名或任务栏托盘菜单直接切换音频输出设备
- **设备别名** — 为设备设置自定义名称（如"耳机"、"音箱"）
- **音量调节** — 每个设备的音量独立记忆，拖动滑块即时生效
- **预设音量** — 低/中/高三档预设，单击应用、双击自定义
- **全局热键** — 可用 Win/Ctrl/Alt/Shift 组合，后台静默响应
- **静音热键** — 一键切换当前设备静音状态
- **开机自启** — 勾选后随系统启动
- **多语言** — 中文 / English

## 🖥️ 系统要求

- Windows 10 / 11
- 无需安装 Python 环境（exe 已打包所有依赖）

## 🚀 快速开始

1. 下载 `小钻风音频切换器_v1.0.exe`
2. 双击运行（程序自动最小化到系统托盘）
3. 右键托盘图标打开设置窗口
4. 配置热键后即可全局切换

## ⌨️ 热键说明

| 功能 | 说明 |
|------|------|
| 循环切换 | 按顺序切换到下一个音频设备 |
| 静音切换 | 切换当前设备静音/取消静音 |
| 设备热键 | 每个设备可绑定独立热键直接切换 |

> **注意**：如果热键与其他程序冲突，请修改为不同组合。

## 📁 文件说明

```
小钻风音频切换器_v1.0/
├── audio_switcher_tray.py    # 源代码（Python 3.12+）
├── 小钻风音频切换器_v1.0.exe  # 打包好的可执行程序
├── icon.ico                  # 程序图标
└── 发布说明_v1.0.md          # 详细发布说明
```

## 🔧 从源码运行

```bash
pip install pycaw comtypes pywin32
python audio_switcher_tray.py
```

## 📦 打包

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --icon=icon.ico --name="小钻风音频切换器_v1.0" audio_switcher_tray.py
```

## 📝 License

MIT

## 👤 作者

这是啥呀 — [18023717@qq.com](mailto:18023717@qq.com)

- GitHub: [@jkl5219](https://github.com/jkl5219/audio-switcher)
- 捐赠支持: [爱发电](https://afdian.com/a/jkl5219)
