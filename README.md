# SL651 水文监测数据模拟上传工具

基于 **SL651-2014《水文监测数据通信规约》** 的遥测站数据模拟工具，提供 Web 界面，可模拟遥测站向中心站上报定时自报报文，并支持报文编解码调试。

![Python](https://img.shields.io/badge/Python-3.8+-blue) ![Flask](https://img.shields.io/badge/Flask-2.3+-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

## 功能特性

- 🖥️ **Web 界面操作**：浏览器打开即用，自动启动本地服务
- 📡 **多目标上报**：支持同时向多个中心站（TCP）发送报文
- 🏞️ **多种站型**：河道、水库、闸坝等站型预设
- 🧮 **要素编码**：雨量、水位、电压、流量、水温、风速等要素的编码/解码
- 🏠 **多地址格式**：支持 HEX、行政区划斜杠分隔（44/01/0001）、BCD 等遥测站地址格式
- 🔍 **报文解析**：内置报文解码器，可反向解析 SL651 报文
- 📦 **独立 EXE**：支持 PyInstaller 打包为免安装可执行文件

## 快速开始

### 方式一：直接运行（推荐）

1. 安装 Python 3.8+
2. 双击 `start.bat`（自动安装依赖并启动）

### 方式二：手动运行

```bash
pip install -r requirements.txt
python app.py
```

启动后浏览器自动打开 `http://127.0.0.1:5000`。

### 方式三：打包为独立 EXE

```bash
build_exe.bat
```

生成 `dist/SL651_Simulator.exe`，无需 Python 环境即可运行。

## 项目结构

```
├── app.py              # Flask Web 后端（接口与页面逻辑）
├── sl651_protocol.py   # SL651-2014 规约编解码核心实现
├── templates/          # Web 前端页面
├── config.json         # 运行配置（目标站、遥测站地址等）
├── requirements.txt    # Python 依赖
├── start.bat           # 一键启动脚本
└── build_exe.bat       # PyInstaller 打包脚本
```

## 使用说明

1. 在「目标设置」中配置中心站的 IP 和端口（如 `127.0.0.6:5001`）
2. 设置遥测站地址（默认 `001255555525`）和站型
3. 在「要素设置」中勾选需要上报的水文要素并填入数值
4. 点击「发送」即可按 SL651 规约编码并通过 TCP 上报
5. 收到的报文可使用内置解码器进行解析验证

> ⚠️ 本工具仅用于联调测试与教学演示，请勿用于正式生产环境的数据伪造。

## License

MIT
