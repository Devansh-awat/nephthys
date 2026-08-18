import logging
import re
from typing import Any
from typing import Dict

from slack_bolt.context.ack.async_ack import AsyncAck
from slack_sdk.web.async_client import AsyncWebClient

from nephthys.database.tables import Macro
from nephthys.database.tables import User
from nephthys.utils.env import env


async def _is_authorized(user_id: str) -> bool:
    user = await User.objects().where(User.slack_id == user_id).first()
    return bool(user and (user.helper or user.admin))


def _check_program_match(command: str) -> bool:
    match = re.match(r"^/(?:add|delete|list)-([\w-]+)-macros$", command)
    if match:
        cmd_prog = match.group(1).replace("-", "_").lower()
        curr_prog = env.program.replace("-", "_").lower()
        return cmd_prog == curr_prog
    return True


async def add_macro_command_callback(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()

    user_id = body.get("user_id", "")
    channel_id = body.get("channel_id", "")
    command = body.get("command", "")
    text = body.get("text", "").strip()

    async def reply(msg: str):
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=msg)

    if not await _is_authorized(user_id):
        await reply(":rac_nooo: Only helpers and admins can add macros.")
        return

    if not _check_program_match(command):
        await reply(
            f":warning: Program mismatch: This bot is configured for `{env.program}`, but the command used was `{command}`."
        )
        return

    if not text:
        await reply(
            f"Usage: `{command} ?<name> <markdown response> [--no-resolve] [--can-run-on-closed]`\n"
            f"Example: `{command} ?faq Check out <https://docs.ai.hackclub.com> --no-resolve`"
        )
        return

    parts = text.split(maxsplit=1)
    macro_name = parts[0].lstrip("?").strip().lower()

    if not macro_name or len(parts) < 2 or not parts[1].strip():
        await reply(f":warning: Please provide a valid macro name and response message (e.g. `{command} ?faq Some response`).")
        return

    raw_message = parts[1].strip()
    resolve_ticket = "--no-resolve" not in raw_message
    can_run_on_closed = "--can-run-on-closed" in raw_message
    message = (
        raw_message.replace("--no-resolve", "")
        .replace("--can-run-on-closed", "")
        .strip()
    )
    if not message:
        await reply(f":warning: Please provide a markdown response for `?{macro_name}`.")
        return

    existing = (
        await Macro.objects()
        .where((Macro.name == macro_name) & (Macro.program == env.program))
        .first()
    )

    if existing:
        await Macro.update(
            {
                Macro.message: message,
                Macro.resolve_ticket: resolve_ticket,
                Macro.can_run_on_closed: can_run_on_closed,
            }
        ).where(Macro.id == existing.id)
        action_verb = "updated"
    else:
        new_macro = Macro(
            name=macro_name,
            message=message,
            resolve_ticket=resolve_ticket,
            can_run_on_closed=can_run_on_closed,
            program=env.program,
        )
        await new_macro.save()
        action_verb = "added"

    logging.info(f"Macro '?{macro_name}' {action_verb} by user {user_id} for program {env.program}")

    flags_summary = (
        f"• Resolves ticket: `{'No' if not resolve_ticket else 'Yes'}`\n"
        f"• Can run on closed tickets: `{'Yes' if can_run_on_closed else 'No'}`"
    )

    await reply(
        f":yay: Successfully {action_verb} macro `?{macro_name}` for *{env.program}*!\n\n"
        f"*Response:*\n{message}\n\n"
        f"*Settings:*\n{flags_summary}"
    )


async def delete_macro_command_callback(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()

    user_id = body.get("user_id", "")
    channel_id = body.get("channel_id", "")
    command = body.get("command", "")
    text = body.get("text", "").strip()

    async def reply(msg: str):
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=msg)

    if not await _is_authorized(user_id):
        await reply(":rac_nooo: Only helpers and admins can delete macros.")
        return

    if not _check_program_match(command):
        await reply(
            f":warning: Program mismatch: This bot is configured for `{env.program}`, but the command used was `{command}`."
        )
        return

    macro_name = text.lstrip("?").strip().lower()
    if not macro_name:
        await reply(f"Usage: `{command} ?<name>`")
        return

    existing = (
        await Macro.objects()
        .where((Macro.name == macro_name) & (Macro.program == env.program))
        .first()
    )

    if existing:
        await Macro.delete().where(Macro.id == existing.id)
        logging.info(f"Macro '?{macro_name}' deleted by user {user_id} for program {env.program}")
        await reply(f":yay: Deleted macro `?{macro_name}` for *{env.program}*.")
    else:
        await reply(f":warning: Macro `?{macro_name}` not found for *{env.program}*.")


async def list_macros_command_callback(
    ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient
) -> None:
    await ack()

    user_id = body.get("user_id", "")
    channel_id = body.get("channel_id", "")
    command = body.get("command", "")

    async def reply(msg: str):
        await client.chat_postEphemeral(channel=channel_id, user=user_id, text=msg)

    if not await _is_authorized(user_id):
        await reply(":rac_nooo: Only helpers and admins can list macros.")
        return

    if not _check_program_match(command):
        await reply(
            f":warning: Program mismatch: This bot is configured for `{env.program}`, but the command used was `{command}`."
        )
        return

    macros = (
        await Macro.objects()
        .where(Macro.program == env.program)
        .order_by(Macro.name)
    )

    if not macros:
        await reply(f"No custom macros found for *{env.program}*.")
        return

    lines = [f"*Custom macros for {env.program}:*"]
    for m in macros:
        flags = []
        if not m.resolve_ticket:
            flags.append("no-resolve")
        if m.can_run_on_closed:
            flags.append("can-run-on-closed")
        flag_str = f" `[{', '.join(flags)}]`" if flags else ""
        lines.append(f"• `?{m.name}`{flag_str} - {m.message[:80]}{'...' if len(m.message) > 80 else ''}")

    await reply("\n".join(lines))
