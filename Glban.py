import re
import time
import typing

from asyncio import sleep as asleep

from telethon.tl.types import Message, User
from .. import loader, utils

BANNED_RIGHTS = {
    "view_messages": False,
    "send_messages": False,
    "send_media": False,
    "send_stickers": False,
    "send_gifs": False,
    "send_games": False,
    "send_inline": False,
    "send_polls": False,
    "change_info": False,
    "invite_users": False,
}

def get_full_name(user: typing.Union[User]) -> str:
    return utils.escape_html(
        f"{user.first_name} " + (user.last_name if getattr(user, "last_name", False) else "")
    ).strip()

@loader.tds
class GlobalRestrict(loader.Module):
    """Global mutation or ban"""

    strings = {
        "name": "GlobalRestrict",
        "no_reason": "Успешные запросы",
        "args": "<b>Неверные аргументы</b>",
        "glban": '<b><a href="{}">{}</a></b>\n<b></b><i>{}</i>\n\n{}',
        "glbanning": " <b>Запрос к TgIP <a href=\"{}\">{}</a>...</b>",
        "in_n_chats": "<b>Кол-во {} </b>",
    }

    def __init__(self):
        self._gban_cache = {}

    @staticmethod
    def convert_time(t: str) -> int:
        try:
            if not str(t)[:-1].isdigit():
                return 0

            if "d" in str(t):
                t = int(t[:-1]) * 60 * 60 * 24
            elif "h" in str(t):
                t = int(t[:-1]) * 60 * 60
            elif "m" in str(t):
                t = int(t[:-1]) * 60
            elif "s" in str(t):
                t = int(t[:-1])

            t = int(re.sub(r"[^0-9]", "", str(t)))
        except ValueError:
            return 0

        return t

    async def args_parser(self, message: Message, include_silent: bool = False) -> tuple:
        args = " " + utils.get_args_raw(message)
        
        if include_silent and " -s" in args:
            silent = True
            args = args.replace(" -s", "")
        else:
            silent = False

        args = args.strip()
        reply = await message.get_reply_message()

        if reply and not args:
            return (
                (await self._client.get_entity(reply.sender_id)),
                0,
                utils.escape_html(self.strings("no_reason")).strip(),
                silent,
            )

        try:
            a = args.split()[0]
            if str(a).isdigit():
                a = int(a)
            user = await self._client.get_entity(a)
        except Exception:
            try:
                user = await self._client.get_entity(reply.sender_id)
            except Exception:
                return False

        t = ([arg for arg in args.split() if self.convert_time(arg)] or ["0"])[0]
        args = args.replace(t, "").replace("  ", " ")
        t = self.convert_time(t)

        if not reply:
            try:
                args = " ".join(args.split()[1:])
            except Exception:
                pass

        if time.time() + t >= 2208978000:
            t = 0

        return (
            user,
            t,
            utils.escape_html(args or self.strings("no_reason")).strip(),
            silent,
        )

    async def ban(self, chat: int, user: typing.Union[User, int], period: int = 0, silent: bool = False):
        if str(user).isdigit():
            user = int(user)

        try:
            await self.inline.bot.kick_chat_member(
                int(f"-100{chat}"),
                int(getattr(user, "id", user)),
            )
        except Exception:
            await self._client.edit_permissions(
                chat,
                user,
                until_date=(time.time() + period) if period else 0,
                **BANNED_RIGHTS,
            )

    @loader.command(
        ru_doc="<реплай | юзер> [причина] [-s] - Забанить пользователя во всех чатах где ты админ",
        en_doc="<replay | user> [reason] [-s] - Ban the user in all chats where you are the admin",
    )
    async def gl(self, message):
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("args"))
            return

        a = await self.args_parser(message, include_silent=True)
        if not a:
            await utils.answer(message, self.strings("args"))
            return

        user, t, reason, silent = a

        msg = await utils.answer(
            message,
            self.strings("glbanning").format(
                utils.get_entity_url(user),
                utils.escape_html(get_full_name(user)),
            ),
        )

        if not self._gban_cache or self._gban_cache.get("exp", 0) < time.time():
            self._gban_cache = {
                "exp": int(time.time()) + 10 * 60,
                "chats": [
                    chat.entity.id
                    async for chat in self._client.iter_dialogs()
                    if (
                        getattr(chat.entity, "admin_rights", None)
                        and getattr(getattr(chat.entity, "admin_rights", None), "ban_users", False) is True
                        and getattr(chat.entity, "participants_count", 6) > 5
                    )
                ],
            }

        chats_text = ""
        counter = 0

        for chat_id in self._gban_cache["chats"]:
            try:
                await asleep(0.05)
                await self.ban(chat_id, user, 0, silent=True)
            except Exception as e:
                error_msg = await utils.answer(msg, f"Ошибка в чате {chat_id}: {e}")
                match = re.search(r'A wait of (\d+) seconds is required', str(e))
                if match:
                    wait_time = match.group(1)
                    await error_msg.delete()
                    await self.invoke("suspend", wait_time, -1003386682154)
                continue
            else:
                counter += 1

        await utils.answer(
            msg,
            self.strings("glban").format(
                utils.get_entity_url(user),
                utils.escape_html(get_full_name(user)),
                reason,
                self.strings("in_n_chats").format(counter) if silent else f"<b>Успешно в {counter} чатах</b>",
            ),
        )
