# QQ 官方 Bot 开发说明

本文档用于《百万美金》插件后续在 QQ 官方机器人场景下持续开发。重点覆盖 AstrBot 插件里最常用的 QQOfficial Markdown 按钮、被动回复上下文、用户 openid 取值和调试流程。

## 基本原则

QQOfficial 群聊与 C2C 开发要优先走“被动回复”路径。用户先发送一条指令，插件再用这条消息的 `msg_id` 和 `msg_seq` 回复按钮消息，可以避免被平台当作无权限的主动群消息。

按钮必须挂在 Markdown 消息下，不能只发送 keyboard：

```json
{
  "msg_type": 2,
  "markdown": {
    "content": "请选择操作"
  },
  "keyboard": {
    "content": {
      "rows": []
    }
  }
}
```

开发时不要把真实 QQ 号、房间密钥、身份信息或结算结果直接放进 `action.data`。`action.data` 对用户可见，尤其 `action.type = 2` 会把它插入输入框。

## AstrBot 事件判断

QQOfficial 插件命令应限制在以下事件类型：

```python
QQOFFICIAL_PLATFORMS = {"qq_official", "qq_official_webhook"}
QQOFFICIAL_MESSAGE_EVENT_NAMES = {
    "QQOfficialMessageEvent",
    "QQOfficialWebhookMessageEvent",
}
QQOFFICIAL_MESSAGE_EVENT_MODULE_PREFIXES = (
    "astrbot.core.platform.sources.qqofficial.",
    "astrbot.core.platform.sources.qqofficial_webhook.",
)
```

判断函数：

```python
def is_qqofficial_message_event(event) -> bool:
    event_type = type(event)
    module_name = event_type.__module__.lower()
    return (
        event_type.__name__ in QQOFFICIAL_MESSAGE_EVENT_NAMES
        and module_name.startswith(QQOFFICIAL_MESSAGE_EVENT_MODULE_PREFIXES)
    )
```

## 被动回复上下文

发送按钮消息前，尽量从原始事件里取引用 ID：

```python
def first_non_empty_str(*values):
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text:
            return text
    return None


def extract_message_reference_id(raw_message, message_obj):
    return first_non_empty_str(
        getattr(raw_message, "id", None),
        getattr(message_obj, "message_id", None),
    )


def add_passive_reply_context(payload, *, msg_id=None, event_id=None, msg_seq=None):
    if msg_id:
        payload["msg_id"] = msg_id
    elif event_id:
        payload["event_id"] = event_id
    if payload.get("msg_id") or payload.get("event_id"):
        payload["msg_seq"] = msg_seq if msg_seq is not None else random.randint(1, 10000)
    return payload
```

群聊与 C2C 发送方式：

```python
raw_message = getattr(event.message_obj, "raw_message", None)
payload = build_message_payload()
add_passive_reply_context(
    payload,
    msg_id=extract_message_reference_id(raw_message, event.message_obj),
    msg_seq=getattr(raw_message, "msg_seq", None),
)

if isinstance(raw_message, botpy.message.GroupMessage):
    await event.bot.api.post_group_message(
        group_openid=raw_message.group_openid,
        **payload,
    )
elif isinstance(raw_message, botpy.message.C2CMessage):
    await event.bot.api.post_c2c_message(
        openid=raw_message.author.user_openid,
        **payload,
    )
```

## 指令按钮

`action.type = 2` 是最稳定的按钮类型。点击后 QQ 客户端会把 `@bot {action.data}` 插入输入框，用户发送后由普通 AstrBot 指令处理。

```json
{
  "id": "mod_start_game",
  "render_data": {
    "label": "开始游戏",
    "visited_label": "已选择开始",
    "style": 1
  },
  "action": {
    "type": 2,
    "permission": {
      "type": 2
    },
    "data": "百万美金开始",
    "reply": true,
    "enter": false,
    "unsupport_tips": "当前客户端不支持该按钮"
  }
}
```

适合《百万美金》的常见按钮：

```text
百万美金创建
百万美金加入
百万美金开始
百万美金状态
百万美金投票 A
百万美金投票 B
```

建议让按钮显示短文本，让 `action.data` 使用完整、明确、可被解析的中文指令。

## 指定用户按钮

如果只想让某个用户操作按钮，可以把 `permission.type` 设为 `0`，并填写 `specify_user_ids`。

```json
{
  "id": "mod_private_confirm",
  "render_data": {
    "label": "确认行动",
    "visited_label": "已确认",
    "style": 1
  },
  "action": {
    "type": 2,
    "permission": {
      "type": 0,
      "specify_user_ids": ["发送者 openid/member_openid"]
    },
    "data": "百万美金确认行动",
    "reply": true,
    "enter": false,
    "unsupport_tips": "当前客户端不支持该按钮"
  }
}
```

发送者 ID 的推荐提取顺序：

```python
def extract_qqofficial_user_openid(event) -> str:
    raw_message = getattr(event.message_obj, "raw_message", None)
    author = getattr(raw_message, "author", None)
    return first_non_empty_str(
        getattr(author, "member_openid", None),
        getattr(raw_message, "group_member_openid", None),
        getattr(author, "user_openid", None),
        getattr(raw_message, "user_openid", None),
        event.get_sender_id() if hasattr(event, "get_sender_id") else None,
    ) or ""
```

注意：`specify_user_ids` 的实际客户端表现需要实测。插件仍应在收到指令后再次校验发送者 openid，不能只依赖按钮客户端限制。

## 回调按钮

`action.type = 1` 是回调按钮。点击后平台应投递 `INTERACTION_CREATE`，插件必须尽快 ACK，否则客户端会一直加载直到请求超时。

```json
{
  "id": "mod_callback_vote_a",
  "render_data": {
    "label": "投票 A",
    "visited_label": "已投 A",
    "style": 1
  },
  "action": {
    "type": 1,
    "permission": {
      "type": 2,
      "specify_user_ids": [],
      "specify_role_ids": []
    },
    "data": "vote_a",
    "click_limit": 0,
    "at_bot_show_channel_list": false,
    "unsupport_tips": "当前客户端不支持该按钮"
  }
}
```

回调事件常用字段：

```text
id                         用于 ACK，也可作为被动回复 event_id
scene                      c2c / group / guild
chat_type                  0 guild, 1 group, 2 C2C
user_openid                C2C 用户 openid
group_openid               群 openid
group_member_openid        群成员 openid
data.resolved.button_id    按钮 id
data.resolved.button_data  按钮 action.data
```

ACK 语义：

```text
PUT /interactions/{interaction_id}
code = 0 表示成功
```

如果 `action.type = 1` 在当前平台始终“请求超时”，优先使用 `action.type = 2` 指令按钮继续开发游戏流程。

## 推荐封装

后续开发建议统一通过一个按钮构造函数生成 payload，避免不同功能各写一套结构：

```python
def build_command_button(button_id: str, label: str, data: str, *, permission=None):
    return {
        "id": button_id,
        "render_data": {
            "label": label,
            "visited_label": label,
            "style": 1,
        },
        "action": {
            "type": 2,
            "permission": permission or {"type": 2},
            "data": data,
            "reply": True,
            "enter": False,
            "unsupport_tips": "当前客户端不支持该按钮",
        },
    }
```

房间、回合、投票、结算等功能都应复用这个 helper。

## 持续开发流程

1. 先实现纯文本指令，例如 `百万美金创建`、`百万美金加入`、`百万美金状态`。
2. 再为高频文本指令补 `action.type = 2` 指令按钮。
3. 每个按钮的 `action.data` 必须等价于一条可手动输入的文本指令。
4. 所有按钮触发后的业务逻辑都要在服务端按 openid 校验权限。
5. 群状态使用 `group_openid` 隔离，不要使用真实 QQ 群号作为数据键。
6. 用户状态使用 `member_openid` / `user_openid`，不要假设能拿到真实 QQ 号。
7. 发按钮失败时回退纯文本菜单，确保官方 Bot 客户端兼容性。
8. 新增按钮或命令后补 pytest，至少覆盖 payload 结构、权限字段和命令解析。
9. 每次修改后更新 `README.md`、`CHANGELOG.md`、`metadata.yaml`，运行测试并打包。

## 调试日志建议

按钮发送前至少记录：

```text
event_class
platform
raw_message class
raw_message.id
raw_message.msg_seq
message_obj.message_id
group_openid
author.user_openid
author.member_openid
最终 payload
API 返回值
```

回调按钮还要记录：

```text
interaction_id
scene
chat_type
button_id
button_data
ACK 返回值
回调回复 API 返回值
```

这些字段足够判断问题属于“按钮没渲染”“被当主动消息”“客户端没投递回调”“ACK 失败”还是“业务指令没有被 AstrBot 捕获”。
