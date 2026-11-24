import json
import os

from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api.star import Context, Star, register

try:
    from astrbot.api.web import request as web_request
    from astrbot.api.web import json_response, error_response
except Exception:  # older/newer API differences: fall back to quart
    web_request = None
    json_response = None
    error_response = None

PLUGIN_NAME = "push_bridge"
BINDINGS_PATH = os.path.join("data", "plugin_data", PLUGIN_NAME, "bindings.json")


@register(PLUGIN_NAME, "wistar", "推送桥：外部系统经 HTTP 接口借机器人往已绑定会话主动发消息", "1.0.0")
class PushBridge(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        if not self._cfg("push_token"):
            try:
                path = os.path.join("data", "config", PLUGIN_NAME + "_config.json")
                with open(path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception:
                pass
        self._bindings = None
        try:
            self.context.register_web_api(
                "/" + PLUGIN_NAME + "/send", self.api_send, ["POST"], "推送一条消息到已绑定会话"
            )
            self.context.register_web_api(
                "/" + PLUGIN_NAME + "/ping", self.api_ping, ["GET"], "健康检查"
            )
        except Exception as e:
            print("[push_bridge] register_web_api failed:", e)

    def _cfg(self, key):
        try:
            value = self.config.get(key, "")
        except Exception:
            value = ""
        return (value or "").strip()

    # ---------- bindings storage ----------
    def _load_bindings(self):
        if self._bindings is None:
            try:
                with open(BINDINGS_PATH, "r", encoding="utf-8") as f:
                    self._bindings = json.load(f)
            except Exception:
                self._bindings = {}
        return self._bindings

    def _save_bindings(self):
        try:
            os.makedirs(os.path.dirname(BINDINGS_PATH), exist_ok=True)
            with open(BINDINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._bindings or {}, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print("[push_bridge] save bindings failed:", e)

    @staticmethod
    def _platform_of(umo):
        return (umo or "").split(":")[0] or "unknown"

    async def _send(self, umo, text):
        chain = MessageChain().message(text)
        await self.context.send_message(umo, chain)

    # ---------- chat commands ----------
    @filter.command("push_bind")
    async def push_bind(self, event: AstrMessageEvent, name: str = ""):
        """把当前会话绑定为推送目标：/push_bind 名称（省略名称则用平台名）"""
        umo = event.unified_msg_origin
        name = (name or "").strip() or self._platform_of(umo)
        bindings = self._load_bindings()
        bindings[name] = umo
        self._save_bindings()
        yield event.plain_result(
            "已绑定推送目标「" + name + "」（" + self._platform_of(umo) + "）。\n"
            "外部系统 POST /api/v1/plugins/extensions/push_bridge/send，"
            "JSON: {\"token\": \"<插件口令>\", \"to\": \"" + name + "\", \"text\": \"内容\"} 即可推送到这里。\n"
            "也可以在任意会话里用 /push_to " + name + " 内容 跨平台发送。"
        )

    @filter.command("push_list")
    async def push_list(self, event: AstrMessageEvent):
        """列出全部已绑定推送目标"""
        bindings = self._load_bindings()
        if not bindings:
            yield event.plain_result("还没有绑定任何推送目标。在想接收推送的会话里发 /push_bind 名称 即可绑定。")
            return
        lines = ["已绑定推送目标（共 " + str(len(bindings)) + " 个）："]
        for name, umo in bindings.items():
            lines.append("- " + name + "｜" + self._platform_of(umo))
        yield event.plain_result("\n".join(lines))

    @filter.command("push_to")
    async def push_to(self, event: AstrMessageEvent, name: str = "", text: str = ""):
        """向已绑定目标发送消息：/push_to 名称 内容"""
        name = (name or "").strip()
        text = (text or "").strip()
        if not name or not text:
            yield event.plain_result("用法：/push_to 名称 内容（先用 /push_list 看已绑定目标）")
            return
        bindings = self._load_bindings()
        umo = bindings.get(name)
        if not umo:
            yield event.plain_result("没有叫「" + name + "」的绑定，先用 /push_list 看列表。")
            return
        try:
            await self._send(umo, text)
            yield event.plain_result("已发送到「" + name + "」。")
        except Exception as e:
            yield event.plain_result("发送失败：" + str(e))

    @filter.command("push_unbind")
    async def push_unbind(self, event: AstrMessageEvent, name: str = ""):
        """解除一个推送目标绑定：/push_unbind 名称"""
        name = (name or "").strip()
        bindings = self._load_bindings()
        if name in bindings:
            del bindings[name]
            self._save_bindings()
            yield event.plain_result("已解除绑定「" + name + "」。")
        else:
            yield event.plain_result("没有叫「" + name + "」的绑定。")

    # ---------- web api ----------
    async def _read_body(self):
        # Prefer astrbot.api.web request proxy; fall back to quart request.
        req = web_request
        if req is None:
            from quart import request as req  # type: ignore
        data = None
        try:
            data = await req.get_json(force=False, silent=True)
        except Exception:
            data = None
        if data is None:
            try:
                raw = await req.get_data()
                if raw:
                    data = json.loads(raw.decode("utf-8", "ignore"))
            except Exception:
                data = None
        headers = {}
        try:
            headers = req.headers or {}
        except Exception:
            headers = {}
        return data or {}, headers

    def _ok(self, payload):
        if json_response is not None:
            return json_response(payload)
        return payload

    def _err(self, msg, status=400):
        if error_response is not None:
            try:
                return error_response(msg, status= status)
            except Exception:
                return error_response(msg)
        return {"ok": False, "error": msg}

    async def api_ping(self):
        return self._ok({"ok": True, "plugin": PLUGIN_NAME})

    async def api_send(self):
        try:
            body, headers = await self._read_body()
        except Exception as e:
            return self._err("bad request: " + str(e))
        token = self._cfg("push_token")
        given = ""
        try:
            given = headers.get("X-Push-Token", "") or ""
        except Exception:
            given = ""
        if not given:
            given = str(body.get("token", "") or "")
        if not token:
            return self._err("plugin token not configured", status=500)
        if given != token:
            return self._err("invalid token", status=403)
        text = str(body.get("text", "") or "").strip()
        if not text:
            return self._err("text is empty")
        to = str(body.get("to", "") or "").strip()
        bindings = self._load_bindings()
        if to in bindings:
            umo = bindings[to]
        elif ":" in to:
            umo = to
        elif len(bindings) == 1:
            umo = next(iter(bindings.values()))
        else:
            return self._err("unknown target: " + to + " (bind it first with /push_bind)")
        try:
            await self._send(umo, text)
        except Exception as e:
            return self._err("send failed: " + str(e), status=500)
        return self._ok({"ok": True, "to": to or "(default)", "platform": self._platform_of(umo)})
