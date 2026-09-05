import asyncio
import logging
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import main
from mentor import DANISH_TUTOR_PROMPT, ENGLISH_TUTOR_PROMPT, LanguageMentor


class FakeCompletions:
    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Svar"))]
        )


class FakeOpenAIClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class MentorMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_is_separate_by_platform_and_user(self):
        discord_mentor = LanguageMentor("discord", ENGLISH_TUTOR_PROMPT)
        telegram_mentor = LanguageMentor("telegram", DANISH_TUTOR_PROMPT)
        discord_mentor._client = FakeOpenAIClient()
        telegram_mentor._client = FakeOpenAIClient()

        await discord_mentor.reply("42", "Hello")
        await discord_mentor.reply("99", "Hi")
        await telegram_mentor.reply("42", "Hej")

        self.assertEqual(set(discord_mentor._histories), {"discord:42", "discord:99"})
        self.assertEqual(set(telegram_mentor._histories), {"telegram:42"})
        self.assertEqual(len(discord_mentor._histories["discord:42"]), 2)
        self.assertEqual(len(telegram_mentor._histories["telegram:42"]), 2)


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def test_missing_environment_variables_have_a_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                main.validate_environment()

    async def test_main_starts_both_runners_concurrently(self):
        discord_started = asyncio.Event()
        telegram_started = asyncio.Event()

        async def fake_discord_runner():
            discord_started.set()
            await asyncio.Event().wait()

        async def fake_telegram_runner():
            telegram_started.set()
            await asyncio.Event().wait()

        discord_module = types.ModuleType("discord_bot")
        discord_module.run_discord_bot = fake_discord_runner
        telegram_module = types.ModuleType("telegram_bot")
        telegram_module.run_telegram_bot = fake_telegram_runner

        environment = {
            "OPENAI_API_KEY": "test",
            "DISCORD_TOKEN": "test",
            "TELEGRAM_TOKEN": "test",
        }
        modules = {
            "discord_bot": discord_module,
            "telegram_bot": telegram_module,
        }

        with patch.dict(os.environ, environment, clear=True), patch.dict(
            sys.modules, modules
        ):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(main.run_bots(), timeout=0.05)

        self.assertTrue(discord_started.is_set())
        self.assertTrue(telegram_started.is_set())

    def test_http_client_info_logs_are_disabled(self):
        main.configure_logging()
        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpcore").level, logging.WARNING)


class TelegramConfigurationTests(unittest.TestCase):
    def test_all_commands_are_registered(self):
        from telegram.ext import CommandHandler

        from telegram_bot import build_telegram_application

        application = build_telegram_application("123:TEST")
        commands = {
            command
            for handler in application.handlers[0]
            if isinstance(handler, CommandHandler)
            for command in handler.commands
        }

        self.assertEqual(
            commands,
            {"start", "help", "exercise", "grammar", "translate", "words"},
        )


class TelegramChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_channel_post_uses_channel_identity_and_sends_a_post(self):
        from telegram_bot import telegram_mentor, text_message

        bot = SimpleNamespace(send_message=AsyncMock())
        message = SimpleNamespace(
            chat_id=-10042,
            sender_chat=SimpleNamespace(id=-10042),
            text="Hej",
            get_bot=lambda: bot,
        )
        update = SimpleNamespace(
            channel_post=message,
            effective_chat=SimpleNamespace(id=-10042),
            effective_message=message,
            effective_user=None,
        )

        reply_mock = AsyncMock(return_value="Hej!")
        with patch.object(telegram_mentor, "reply", reply_mock):
            await text_message(update, None)

        reply_mock.assert_awaited_once_with("channel:-10042", "Hej")
        bot.send_message.assert_awaited_once_with(chat_id=-10042, text="Hej!")


if __name__ == "__main__":
    unittest.main()
