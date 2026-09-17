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
- 🗣️ DU3 Opgave 2 — audio-first speaking practice for Modul 3
- 🧪 Tests
- 📚 Grammar
- ✍️ Writing
- 🔤 Verbs

The DU3 Opgave 2 mode currently includes five prepared themes: *At lære dansk*,
*At møde nye venner*, *Bolig*, *Grønne vaner*, and *Sunde og usunde vaner*.
For each theme the learner practices four paired situations by asking a
question, hearing a short spoken answer, and answering a question back. The
mode then continues to an individual examiner-style part with four questions.
Important Danish mistakes are corrected briefly, and both voice messages and
typed answers are accepted while the session is active.

Generated topic exercises stay in five-question blocks. After each completed
block the learner can choose **Fem nye om emnet** to continue the same topic for as
many blocks as desired. The generator receives up to 30 recently used questions
for that topic and is instructed to avoid repeats and close paraphrases.

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

## Danish reading dialogues

Open **Test → Dialoger — læsning**, or use `/dialogues`.

- **Som til prøven** shows the whole conversation, three gaps and A–F options
  (three unused). Submit `1F 2D 3B` or `FDB`; results appear after all answers.
- **Øvelse** keeps both surrounding lines visible and accepts one letter or
  button per gap, with immediate Russian explanations and translations of clues.
- Generate original A2/B1 everyday dialogues about transport, shopping, housing,
  work, invitations or family, or enter your own topic. **En lignende opgave** generates
  another dialogue on the same topic and avoids the 15 recent situations.
- **Tilføj opgave** accepts text or a photo (up to 10 MB). Include the full
  conversation and six options. The bot shows an editable-by-resubmission preview;
  **Gem og start** saves it to that user's **Mine opgaver**.
- **Øv dine fejl** lists recent completed dialogues with mistakes; retrying
  creates a new attempt. Lists show the most recent 15 matching records.
- **Fortsæt** inside the dialogues menu resumes an unfinished dialogue, including
  after restart. Leaving the mode pauses it so other activities can receive text.

Generation/import validates the schema, then independently solves the task without
seeing the proposed key, and checks Russian feedback in a separate call. Failed
validation gets up to two repair attempts that receive the previous candidate and
specific rejection feedback. The reviewer receives a speaker-labelled transcript,
explicit gaps and both neighbouring lines, and must identify exactly one candidate
per gap. Generation has a 60-second overall deadline; unusable tasks are not shown.
These model checks reduce
ambiguity but are not a guarantee of linguistic accuracy. Typed answers are graded
locally against the saved key, with no model-based grading. Imported handwritten
answers are treated as guesses rather than an authoritative key.

All static Telegram menus, topics, navigation, status and progress messages are in
Danish. Russian input aliases remain accepted; learning explanations and vocabulary
translations remain in Russian.

If generation fails or times out, the six standard topics have hand-reviewed reserve
exercises in `dialogue_examples.py`. These are clearly labelled as prepared exercises.
Letters are shuffled without changing the answer mapping. If the reserve has already
been seen, the bot explicitly calls it repetition. Custom topics without a matching
reserve show a retry/choose-another-topic message. Imports never substitute a reserve
for the learner's source. Database failures are reported separately from generation.

The new `dialogue_sessions` table is created automatically and stores private
exercises, answers and attempts through the existing learner profile. Completed
attempts contribute to Tests statistics once; opening/generating a task does not.
The existing confirmed `/reset_progress` also deletes that learner's saved dialogues.
No new environment variables or packages are required. Generation uses `OPENAI_MODEL`;
photo transcription uses the existing `OPENAI_VISION_MODEL` setting.

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
