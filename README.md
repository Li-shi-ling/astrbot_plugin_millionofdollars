# astrbot_plugin_millionofdollars

《百万美金》（Millions of Dollars）桌游的 AstrBot 插件项目。

当前版本已完成规则资料归档和 QQ 官方 Bot 开发实现设计，后续游戏功能以 2016 年初版规则为实现基线。

## 规则文档

- [完整中文规则](./docs/million-of-dollars-rules-zh.md)
- [资料来源与版本说明](./docs/README.md)
- [QQ 官方 Bot 开发说明](./docs/qqofficial-bot-development.md)
- [QQ 官方 Bot 游戏开发实现设计](./docs/game-implementation-design.md)
- [2016 初版英文规则书 PDF](./docs/sources/millions-of-dollars-2016-rulebook-en.pdf)
- [2024 二版英文规则书 PDF](./docs/sources/millions-of-dollars-2024-rulebook-en.pdf)

2016 初版与 2024 二版的轮数、胜利金额和角色体系均不同，插件开发不得混用两个版本的规则。

## 项目状态

插件代码目前仍处于模板初始化阶段，尚未提供可玩的《百万美金》游戏指令。v1.3.3 已冻结房间状态机、HMAC 按钮、独立转账/退出、威胁牌按钮、SQLite 持久化及测试验收方案，供后续编码直接执行。

## 相关链接

- [AstrBot 项目](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档](https://docs.astrbot.app/dev/star/plugin-new.html)
