# English and Danish Mentor Bots

One Python process runs two language-learning bots concurrently:

- Discord bot — English mentor with chat, exercises, grammar correction,
  image recognition, speech-to-text, text-to-speech, and interaction logging.
- Telegram bot — Danish mentor with conversation practice, corrections,
  translation, exercises, and vocabulary training. It can answer private
  messages and channel posts when it has permission to post in the channel.

Conversation history is stored separately in memory for every platform and
user (`discord:<user_id>` and `telegram:<user_id>`). This short conversation
history resets when the process restarts. Long-term study state is stored in a
database and remains separate from conversation history. Discord interaction
logs continue to be written to `user_data/`.

## Long-term Danish study memory

The Telegram mentor has an inline study menu with these sections:

- 🎧 Audio
- 🧪 Tests
- 📚 Grammar
- ✍️ Writing
- 🔤 Verbs

`/continue` reads the stored profile and resumes an unfinished quiz or shows the
last topic and next step. `/progress`, `/history`, and `/review` are also built
from stored records rather than guesses made by the language model.

Study progress is recorded only after a concrete action succeeds, such as a
completed quiz, a submitted writing task, a processed audio task selected from
the study menu, or a verb review answer. Merely viewing or generating an
exercise does not increase progress.

The A1 plan currently contains 10 tasks in each of five equally weighted
sections. Section progress is `completed_tasks / total_tasks`, capped at 100%.
Overall progress is the weighted average of the five sections. It describes
progress inside the current A1 plan, not the percentage of the Danish language
the learner knows. A language level is never raised automatically from this
percentage.

Verb reviews use a deliberately simple interval schedule after successful
answers: 1, 3, 7, 14, then 30 days. A wrong answer shortens the streak by one,
sets the verb to `review`, and schedules it for the next day. A verb becomes
`mastered` only after five successful review steps. Review attempts are stored,
so pressing the same inline button again cannot increment progress twice.

### Database schema

SQLAlchemy creates the following tables non-destructively with `create_all`:

- `learner_profiles` — platform/user/language, A1 level, current section/topic,
  activity timestamps, and next step;
- `section_progress` — task and answer counters plus the latest topic/score;
- `grammar_topics` — `new`, `learning`, `review`, or `mastered` state and review
  dates;
- `learner_errors` — recurring error examples, corrections, counts, and review
  dates;
- `verb_progress` and `verb_review_attempts` — Danish forms, Russian meaning,
  counters, status, interval dates, and idempotent answers;
- `vocabulary_items` — storage for vocabulary review items;
- `exercise_results` — concrete completed audio/test/grammar/writing/verb work;
- `quiz_sessions` — persistent in-progress and completed quizzes.

Records are keyed through a learner profile whose unique identity is
`platform + user_id + language`, so Telegram, Discord, and different users do
not share study data. Table initialization never drops existing records.

## Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | OpenAI API key used by both mentors |
| `DISCORD_TOKEN` | Yes | Discord bot token |
| `TELEGRAM_TOKEN` | Yes | Telegram bot token |
| `OPENAI_MODEL` | No | Chat model; defaults to `gpt-4o-mini` |
| `DATABASE_URL` | Production | PostgreSQL URL; without it local development falls back to `sqlite:///study_memory.db` |

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
- `/learn`
- `/continue`
- `/progress`
- `/history`
- `/review`
- `/reset_progress` (requires confirmation)
- `/exercise [topic]`
- `/grammar <Danish phrase>`
- `/translate <Russian or Danish text>`
- `/words [topic]`
- `/verbs`

## Render

Keep a single **Background Worker** service connected to this repository.

- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Environment: set `OPENAI_API_KEY`, `DISCORD_TOKEN`, `TELEGRAM_TOKEN`, and
  `DATABASE_URL`; optionally set `OPENAI_MODEL`.

Create a Render PostgreSQL database and copy its internal connection URL into
the worker's `DATABASE_URL`. Render files are ephemeral, so the SQLite fallback
is for local development only. The application accepts Render-style
`postgres://` and standard `postgresql://` URLs and selects the Psycopg 3 driver
automatically. Do not commit a database URL or password.

The database tables are initialized automatically before both bots start. Keep
the existing single Background Worker and the same start command; Discord and
Telegram still run together in one process.

The speech feature uses `pydub` and requires `ffmpeg` in the Render runtime.
