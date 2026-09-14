# 赃物牌组核验

> 状态：**未完成**。牌组核验前插件无法开局。

## 为什么必须单独核验

《百万美金》2016 初版共有 10 张赃物牌，每张标明：

- 可分赃款（原版范围为 800 万～1200 万美元）；
- 每人保证金（100 万或 200 万美元）；
- 部分牌面标有一个额外获益角色符号。

规则正文只给出取值范围，没有逐张牌面。归档的
[2016 英文规则书 PDF](./sources/millions-of-dollars-2016-rulebook-en.pdf)
只有 4 页，含组件示意图，**不含牌面数值**。

`docs/game-implementation-design.md` 第 4.3 节因此规定：

> 规则正文只给出了金额和保证金范围，开发时不得凭范围臆造 10 张牌面；
> 录入牌组的提交必须附逐张核验测试或来源截图索引。

当前代码状态：

- `game/loot.py` 的 `LOOT_CARD_DATA` 为空元组；
- `LOOT_DECK_VERIFIED = False`；
- `build_deck()` 抛 `DeckNotVerifiedError`；
- `百万美金 开始` 会回复“暂时无法开局：赃物牌组尚未逐张核验……”。

其余游戏逻辑（选角、谈判、结算、分赃、胜利、HMAC 令牌、SQLite 持久化）
均已实现并通过测试，只等牌面数据。

## 核验步骤

1. 准备实物牌或官方牌面资料（实物拍照、出版商成品图、官方 PnP 文件）。
2. 逐张记录 `card_id`、`amount`、`ante`、`bonus_role`。
3. 把 10 张牌写入 `game/loot.py` 的 `LOOT_CARD_DATA`，每张牌的 `card_id`
   使用形如 `loot-01` 的稳定编号。
4. 把对应的来源写入 `LOOT_DECK_SOURCE_INDEX`，每项说明该张牌的出处
   （例如 `loot-01: 实物正面照片 card-face-01.jpg`）。索引数量必须与牌面数量一致。
5. 把 `LOOT_DECK_VERIFIED` 置为 `True`。
6. 在 `tests/test_tokens.py` 增加一条断言，把 10 张牌面写成期望常量，
   防止后续误改。
7. 运行 `python -m pytest tests/`，再运行 `python scripts/package_plugin.py`。

## 合法性校验

`game/loot.py` 的 `validate_deck()` 会自动拒绝以下数据：

- 张数不等于 10；
- `card_id` 为空或重复；
- `amount` 不是整数或不在 800 万～1200 万；
- `ante` 不是 100 万或 200 万；
- `bonus_role` 不是五种角色之一。

这些约束由 `tests/test_tokens.py` 覆盖。
