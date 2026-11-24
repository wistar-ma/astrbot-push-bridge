# 推送桥 push_bridge

让外部系统（n8n、青龙、脚本等）借 AstrBot 往已绑定的会话主动发消息。

## 用法

1. 在想接收推送的会话里发 `/push_bind 名称`（如在 Telegram 私聊发 `/push_bind tg`）。
2. 在插件配置里设置 `push_token` 口令。
3. 外部系统调用：
   `POST http://<astrbot地址>/api/v1/plugins/extensions/push_bridge/send`
   Header: `X-Push-Token: <口令>`，JSON: `{"to": "tg", "text": "要推送的内容"}`
   （`to` 也可直接传 unified_msg_origin；只有一个绑定时可省略。）
4. 聊天内跨平台发送：`/push_to 名称 内容`；`/push_list` 看全部绑定；`/push_unbind 名称` 解绑。

健康检查：`GET /api/v1/plugins/extensions/push_bridge/ping`
