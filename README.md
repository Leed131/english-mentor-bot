# English and Danish Mentor Bots

One Python process runs two language-learning bots concurrently:

- Discord bot — English mentor with chat, exercises, grammar correction,
  image recognition, speech-to-text, text-to-speech, and interaction logging.
- Telegram bot — Danish mentor with conversation practice, corrections,
  translation, exercises, and vocabulary training.

Conversation history is stored separately in memory for every platform and
user (`discord:<user_id>` and `telegram:<user_id>`). It resets when the process
restarts. Discord interaction logs continue to be written to `user_data/`.

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI API key used by both mentors |
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `TELEGRAM_TOKEN` | Yes | Telegram bot token |
| `OPENAI_MODEL` | No | Chat model; defaults to `gpt-4o-mini` |

Never commit real tokens. Use `.env.example` only as a reference; the
application reads values from the process environment.

## Local setup

```bash
python -m venv .venv
pip install -r requirements.txt
```

Set all required environment variables in your shell, then start both bots:

```bash
python main.py
```

Telegram commands:

- `/start`
- `/help`
- `/exercise [topic]`
- `/grammar <Danish phrase>`
- `/translate <Russian or Danish text>`
- `/words [topic]`

## Render

Keep a single **Background Worker** service connected to this repository.

- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Environment: set `OPENAI_API_KEY`, `DISCORD_TOKEN`, and `TELEGRAM_TOKEN`;
  optionally set `OPENAI_MODEL`.

The speech feature uses `pydub` and requires `ffmpeg` in the Render runtime.
