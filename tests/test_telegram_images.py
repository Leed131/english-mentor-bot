import unittest
from types import SimpleNamespace

from telegram.ext import MessageHandler

from telegram_image_support import (
    _image_file_id,
    _vision_instruction,
    image_message,
    install_telegram_image_support,
)


class TelegramImageSupportTests(unittest.TestCase):
    def test_photo_uses_largest_telegram_size(self):
        message = SimpleNamespace(
            photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")],
            document=None,
        )
        self.assertEqual(_image_file_id(message), "large")

    def test_supported_image_document_is_accepted(self):
        message = SimpleNamespace(
            photo=[],
            document=SimpleNamespace(file_id="doc", mime_type="image/png"),
        )
        self.assertEqual(_image_file_id(message), "doc")

    def test_instruction_contains_caption_and_learner_context(self):
        prompt = _vision_instruction(
            "Объясни эту грамматику",
            "Level: A1; Current topic: word order",
        )
        self.assertIn("Объясни эту грамматику", prompt)
        self.assertIn("Level: A1", prompt)
        self.assertIn("Do not claim the learner completed", prompt)

    def test_installer_adds_image_message_handler(self):
        import telegram_bot

        original_builder = telegram_bot.build_telegram_application
        had_flag = getattr(telegram_bot, "_image_support_installed", False)
        if had_flag:
            delattr(telegram_bot, "_image_support_installed")

        try:
            install_telegram_image_support()
            application = telegram_bot.build_telegram_application("123:TEST")
            handlers = application.handlers[0]
            self.assertTrue(
                any(
                    isinstance(handler, MessageHandler)
                    and handler.callback is image_message
                    for handler in handlers
                )
            )
        finally:
            telegram_bot.build_telegram_application = original_builder
            if hasattr(telegram_bot, "_image_support_installed"):
                delattr(telegram_bot, "_image_support_installed")


if __name__ == "__main__":
    unittest.main()
