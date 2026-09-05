import asyncio
import logging
import os


REQUIRED_ENVIRONMENT_VARIABLES = (
    "OPENAI_API_KEY",
    "DISCORD_TOKEN",
    "TELEGRAM_TOKEN",
)


def validate_environment() -> None:
    missing = [name for name in REQUIRED_ENVIRONMENT_VARIABLES if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {names}")


async def run_bots() -> None:
    validate_environment()

    from discord_bot import run_discord_bot
    from telegram_bot import run_telegram_bot

    tasks = {
        asyncio.create_task(run_discord_bot(), name="Discord bot"),
        asyncio.create_task(run_telegram_bot(), name="Telegram Danish bot"),
    }

    try:
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        finished = done.pop()
        if finished.cancelled():
            raise RuntimeError(f"{finished.get_name()} was cancelled")

        error = finished.exception()
        if error is not None:
            raise error

        raise RuntimeError(f"{finished.get_name()} stopped unexpectedly")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)

    try:
        asyncio.run(run_bots())
    except Exception as error:
        logging.error("Bot process stopped: %s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
