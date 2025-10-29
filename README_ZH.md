# AITradeGame - 面向 A 股市场的 AI 交易模拟器

[English](README.md) | [中文](README_ZH.md)

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AITradeGame 是专注于中国大陆 A 股市场的开源交易模拟器。它将大型语言模型（LLM）的推理能力与沪深股市行情数据结合，帮助你在符合监管约束的环境中快速搭建、测试并对比基于 AI 的交易策略。项目同时提供本地桌面模式与带排行榜的在线体验。

## 主要特性

### 为 A 股而生
- 基于 AkShare 的实时行情、基本面与涨跌停价格
- 了解交易日历、节假日与 T+1 交割限制
- 贴合内地交易所规则的手续费与最小交易单位仿真
- 自动补充持仓的板块、停牌、涨跌停等信息

### AI 策略工作台
- 多家 API 提供方统一管理，可自动拉取 OpenAI 协议模型清单
- 可配置的交易频率与费率，让策略调度更灵活
- 聚合看板对比多模型表现，掌握收益曲线与风险指标
- 基于 ECharts 的可视化、历史净值与交易日志

### 部署方式灵活
- 本地桌面版本，数据全部存储在 SQLite，守护隐私
- 可选的 Web 托管版本，支持后台运行与排行榜
- 提供容器镜像，方便接入现有基础设施

## 快速开始

### 在线体验
访问 https://aitradegame.com 即可直接体验界面与排行榜，无需本地安装。

### 桌面（本地）部署
1. 克隆本仓库
2. 安装依赖：`pip install -r requirements.txt`
3. 启动应用：`python app.py`
4. 打开浏览器访问 http://localhost:5000 ，开始配置提供方和模型

> AkShare 依赖 pandas 与 numpy。准备全新 Python 环境时，请确保能够安装对应的 wheel（或具备从源码构建的能力），再启动应用。

### Docker 部署
同样可以借助 Docker 运行 AITradeGame：

**使用 docker-compose（推荐）：**
```bash
# 构建并启动容器
docker-compose up -d

# 访问应用 http://localhost:5000
```

**直接使用 docker：**
```bash
# 构建镜像
docker build -t aitradegame .

# 运行容器
docker run -d -p 5000:5000 -v $(pwd)/data:/app/data aitradegame

# 访问应用 http://localhost:5000
```

`data/` 目录用于存放 SQLite 数据库（`AITradeGame.db`）。完成后可通过 `docker-compose down` 停止服务。

## 配置指引

### 配置 AI 提供方
1. 点击顶部的 **API Provider**
2. 输入名称、API 基地址与密钥
3. 可自动获取模型列表，也可以手动录入
4. 保存后即可在所有模型中复用该提供方

### 添加交易模型
1. 点击 **Add Model**
2. 选择已配置的提供方
3. 选择模型，设置展示名称与初始资金（人民币）
4. 将市场类型设置为 **A-share**，确认后即开始模拟循环

### 系统设置
通过 **Settings** 面板可以：
- 调整 **Trading Frequency**，控制策略决策间隔（1–1440 分钟）
- 设置 **Trading Fee Rate**，默认万一（0.1%）单边手续费
- A 股模式下会自动执行 100 股一手、禁止卖空等约束

### 进阶配置（可选）
`config.example.py` 展示了默认行为，可用于：
- 修改数据库文件位置
- 开关自动交易与自定义轮询间隔
- 定义默认的 A 股自选列表（`A_SHARE_SYMBOLS`）
- 调整 AkShare 行情与基本面缓存时长

如需长期覆盖配置，将其复制为 `config.py` 并按需修改。

## 开发说明

开发需要 Python 3.9 及以上版本，并需连接网络以访问 AkShare 与 LLM API。安装依赖：

```bash
pip install -r requirements.txt
```

### 验证清单
提交文档或配置改动前，请执行以下关键字扫描，确保共享模板中不会重新出现非 A 股术语：

```bash
grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
     --include="CHANGELOG.md" -n "crypto" .
grep -R --include="config*.py" --include="docker-compose.yml" --include="Dockerfile" \
     --include="CHANGELOG.md" -n "coin" .
```

在仅包含 A 股内容的情况下，这两条命令都不应返回任何结果。

## 隐私与安全
所有数据均保存于本地的 `AITradeGame.db` SQLite 文件中，除非你主动配置外部的 AI 提供方。系统不创建账户，也不会回传任何隐私信息。

## 贡献
欢迎社区贡献！请查阅 [CONTRIBUTING.md](CONTRIBUTING.md) 获取详细规范。

## 免责声明
AITradeGame 仅用于策略研究与教学实验，不会执行真实交易，也不会接触真实资金。投资前请务必自行做好风险评估。

## 相关链接
- 带排行榜的在线版本：https://aitradegame.com
- 桌面版下载：https://github.com/chadyi/AITradeGame/releases/tag/main
- 源码仓库：https://github.com/chadyi/AITradeGame
