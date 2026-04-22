import json
import html
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI
from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


load_dotenv()

def sanitize_secret(value: str) -> str:
    # Remove accidental spaces/newlines copied from dashboards.
    return re.sub(r"\s+", "", (value or "").strip())


TELEGRAM_BOT_TOKEN = sanitize_secret(os.getenv("TELEGRAM_BOT_TOKEN", ""))
OPENAI_API_KEY = sanitize_secret(os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip()
TELEGRAM_CONNECT_TIMEOUT = float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "30"))
TELEGRAM_READ_TIMEOUT = float(os.getenv("TELEGRAM_READ_TIMEOUT", "30"))
TELEGRAM_WRITE_TIMEOUT = float(os.getenv("TELEGRAM_WRITE_TIMEOUT", "30"))
TELEGRAM_POOL_TIMEOUT = float(os.getenv("TELEGRAM_POOL_TIMEOUT", "10"))
TELEGRAM_BOOTSTRAP_RETRIES = int(os.getenv("TELEGRAM_BOOTSTRAP_RETRIES", "5"))


if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")


client = OpenAI(api_key=OPENAI_API_KEY)


@dataclass
class QuizQuestion:
    prompt_ru: str
    correct_answer: str
    alt_answers: List[str] = field(default_factory=list)


@dataclass
class LogicQuestion:
    question_text: str
    answer: str
    voice_hint: str = ""


@dataclass
class SessionState:
    source_text: str = ""
    japanese_text: str = ""
    vocab: List[Dict[str, str]] = field(default_factory=list)
    vocab_questions: List[QuizQuestion] = field(default_factory=list)
    vocab_idx: int = 0
    logic_questions: List[LogicQuestion] = field(default_factory=list)
    logic_idx: int = 0
    stars: int = 0
    points: int = 0
    phase: str = "idle"


USER_STATE: Dict[int, SessionState] = {}


def get_state(user_id: int) -> SessionState:
    if user_id not in USER_STATE:
        USER_STATE[user_id] = SessionState()
    return USER_STATE[user_id]


def normalize(s: str) -> str:
    s = s.strip().lower()
    return re.sub(r"\s+", "", s)


def ai_json(prompt: str) -> Dict[str, Any]:
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    raw_text = response.output_text
    return json.loads(raw_text)


def check_openai_api() -> None:
    # Cheap startup check to fail fast on invalid key/network
    client.models.list()


def analyze_text_for_japanese_learning(user_text: str) -> Dict[str, Any]:
    prompt = f"""
Ты ИИ-методист японского языка.
Пользовательский текст:
{user_text}

Сделай:
1) Переведи текст на японский естественно.
2) Выдели ВСЕ смысловые слова из японского текста (частицы НЕ включать).
3) Если слово - глагол, дай словарную форму.
4) Для каждого слова дай:
   - "word": японское написание (кандзи/кана)
   - "reading_hiragana": чтение только на хирагане.
     Если слово обычно пишется на катакане и хирагана не нужна - верни пустую строку.
   - "translation_ru": перевод на русский.
   - "base_form_note": если поменял форму (например глагол) - что изменил, иначе пусто.
5) Добавь короткий комментарий по переводу.

Ответ строго JSON:
{{
  "japanese_translation": "...",
  "comment_ru": "...",
  "vocab": [
    {{
      "word": "...",
      "reading_hiragana": "...",
      "translation_ru": "...",
      "base_form_note": "..."
    }}
  ]
}}
"""
    data = ai_json(prompt)
    if "vocab" not in data or not isinstance(data["vocab"], list):
        data["vocab"] = []
    return data


def generate_logic_questions(japanese_text: str) -> List[LogicQuestion]:
    prompt = f"""
Сгенерируй 3 коротких вопроса на логику или математику на основе этого японского текста:
{japanese_text}

Требования:
- каждый вопрос на японском;
- вопрос должен иметь однозначный короткий ответ;
- ответ верни строкой;
- вопросы должны быть решаемыми по смыслу текста + простой логике/арифметике.

Верни JSON:
{{
  "questions": [
    {{
      "question_text": "...",
      "answer": "...",
      "voice_hint": "краткая подсказка как интонационно озвучить вопрос"
    }}
  ]
}}
"""
    data = ai_json(prompt)
    items = data.get("questions", [])
    result: List[LogicQuestion] = []
    for item in items[:3]:
        q = LogicQuestion(
            question_text=str(item.get("question_text", "")).strip(),
            answer=str(item.get("answer", "")).strip(),
            voice_hint=str(item.get("voice_hint", "")).strip(),
        )
        if q.question_text and q.answer:
            result.append(q)
    return result


def get_yojijukugo_card() -> Dict[str, str]:
    prompt = """
Дай один японский фразеологизм/ёдзидзюкуго.
Верни JSON:
{
  "phrase": "四字熟語",
  "reading": "ひらがな",
  "meaning_ru": "краткий смысл на русском",
  "example_jp": "короткий пример на японском",
  "example_ru": "перевод примера на русском"
}
"""
    return ai_json(prompt)


def synthesize_japanese_voice(text: str, filename: str) -> str:
    with client.audio.speech.with_streaming_response.create(
        model=OPENAI_TTS_MODEL,
        voice=OPENAI_TTS_VOICE,
        input=text,
        instructions="Speak in natural Japanese with clear pronunciation.",
        response_format="opus",
    ) as response:
        response.stream_to_file(filename)
    return filename


def build_vocab_questions(vocab: List[Dict[str, str]]) -> List[QuizQuestion]:
    result: List[QuizQuestion] = []
    for item in vocab:
        word = str(item.get("word", "")).strip()
        translation_ru = str(item.get("translation_ru", "")).strip()
        if not word or not translation_ru:
            continue
        prompt_ru = f"Как по-японски: {translation_ru}?"
        result.append(
            QuizQuestion(
                prompt_ru=prompt_ru,
                correct_answer=word,
                alt_answers=[],
            )
        )
    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Отправь любой текст на любом языке.\n\n"
        "Я:\n"
        "1) Переведу его на японский.\n"
        "2) Сделаю словарь (без частиц, глаголы в словарной форме, чтение на хирагане).\n"
        "3) Проведу тест по словам и начислю звезды.\n"
        "4) Отправлю озвучку японского текста.\n"
        "5) Задам вопросы на логику/математику по содержанию и начислю баллы.\n"
        "6) Отправлю карточку с ёдзидзюкуго."
    )
    await update.message.reply_text(text)


async def score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state = get_state(user_id)
    await update.message.reply_text(
        f"Твой счет: ⭐ {state.stars} | 🏆 {state.points} баллов | этап: {state.phase}"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    USER_STATE[user_id] = SessionState()
    await update.message.reply_text("Прогресс сброшен. Можешь отправить новый текст.")


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    proxy_state = "enabled" if TELEGRAM_PROXY_URL else "disabled"
    try:
        check_openai_api()
        openai_state = "ok"
    except Exception as exc:
        openai_state = f"error: {exc}"
    await update.message.reply_text(
        "Проверка подключения:\n"
        f"- Telegram proxy: {proxy_state}\n"
        f"- OpenAI API: {openai_state}"
    )


async def run_vocab_question(update: Update, state: SessionState) -> None:
    if state.vocab_idx >= len(state.vocab_questions):
        state.phase = "logic_quiz"
        await update.message.reply_text("Тест по словам завершен. Теперь вопросы на логику и расчет.")
        for i, question in enumerate(state.logic_questions, start=1):
            spoiler_text = html.escape(question.question_text)
            await update.message.reply_text(
                f"Вопрос {i} (текст можно открыть): <tg-spoiler>{spoiler_text}</tg-spoiler>",
                parse_mode=ParseMode.HTML,
            )

            with tempfile.NamedTemporaryFile(delete=False, suffix=".opus") as tmp_voice:
                synthesize_japanese_voice(question.question_text, tmp_voice.name)
                with Path(tmp_voice.name).open("rb") as f:
                    await update.message.reply_voice(voice=InputFile(f))
                Path(tmp_voice.name).unlink(missing_ok=True)

        if state.logic_questions:
            await update.message.reply_text("Ответь на вопрос 1:")
        else:
            await finish_session(update, state)
        return

    q = state.vocab_questions[state.vocab_idx]
    await update.message.reply_text(
        f"Слово {state.vocab_idx + 1}/{len(state.vocab_questions)}\n{q.prompt_ru}\n"
        "Введи ответ японскими символами."
    )


async def run_logic_question(update: Update, state: SessionState) -> None:
    if state.logic_idx >= len(state.logic_questions):
        await finish_session(update, state)
        return
    q = state.logic_questions[state.logic_idx]
    await update.message.reply_text(
        f"Логика {state.logic_idx + 1}/{len(state.logic_questions)}:\n{q.question_text}"
    )


async def finish_session(update: Update, state: SessionState) -> None:
    card = get_yojijukugo_card()
    phrase = card.get("phrase", "一期一会")
    reading = card.get("reading", "いちごいちえ")
    meaning_ru = card.get("meaning_ru", "Цени каждую встречу как уникальную.")
    example_jp = card.get("example_jp", "一期一会の気持ちで、今日を大切にしよう。")
    example_ru = card.get("example_ru", "С настроем «один шанс, одна встреча» ценим этот день.")

    state.phase = "done"
    rank = "Новичок"
    if state.points >= 18:
        rank = "Сенсей"
    elif state.points >= 10:
        rank = "Сэмпай"
    elif state.points >= 5:
        rank = "Ученик"

    await update.message.reply_text(
        f"Финальный результат:\n⭐ {state.stars}\n🏆 {state.points} баллов\n🎓 Ранг: {rank}"
    )
    await update.message.reply_text(
        "Визитная карточка бота:\n"
        f"🈶 {phrase}\n"
        f"🔤 {reading}\n"
        f"💡 {meaning_ru}\n\n"
        f"Пример: {example_jp}\n"
        f"Перевод: {example_ru}"
    )


async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    state = get_state(user_id)
    incoming = update.message.text.strip()

    if state.phase == "vocab_quiz":
        q = state.vocab_questions[state.vocab_idx]
        user_ans = normalize(incoming)
        valid_answers = [normalize(q.correct_answer)] + [normalize(a) for a in q.alt_answers]
        if user_ans in valid_answers:
            state.stars += 1
            state.points += 2
            await update.message.reply_text("✅ Верно! +1⭐ и +2 балла")
        else:
            await update.message.reply_text(f"❌ Неверно. Правильно: {q.correct_answer}")
        state.vocab_idx += 1
        await run_vocab_question(update, state)
        return

    if state.phase == "logic_quiz":
        q = state.logic_questions[state.logic_idx]
        if normalize(incoming) == normalize(q.answer):
            state.points += 4
            await update.message.reply_text("✅ Верный ответ! +4 балла")
        else:
            await update.message.reply_text(f"❌ Неверно. Верный ответ: {q.answer}")
        state.logic_idx += 1
        await run_logic_question(update, state)
        return

    try:
        state.source_text = incoming
        await update.message.reply_text("Анализирую текст и готовлю перевод с учебными материалами...")

        data = analyze_text_for_japanese_learning(incoming)
        state.japanese_text = str(data.get("japanese_translation", "")).strip()
        state.vocab = list(data.get("vocab", []))
        state.vocab_questions = build_vocab_questions(state.vocab)
        state.vocab_idx = 0
        state.logic_idx = 0
        state.stars = 0
        state.points = 0
        state.phase = "vocab_quiz"

        comment_ru = str(data.get("comment_ru", "")).strip()
        await update.message.reply_text(f"Перевод на японский:\n\n{state.japanese_text}")
        if comment_ru:
            await update.message.reply_text(f"Комментарий: {comment_ru}")

        if state.vocab:
            lines = []
            for i, item in enumerate(state.vocab, start=1):
                word = item.get("word", "")
                reading = item.get("reading_hiragana", "")
                tr = item.get("translation_ru", "")
                note = item.get("base_form_note", "")
                reading_part = f" [{reading}]" if reading else ""
                note_part = f" ({note})" if note else ""
                lines.append(f"{i}. {word}{reading_part} - {tr}{note_part}")
            await update.message.reply_text("Словарь:\n" + "\n".join(lines))
        else:
            await update.message.reply_text("Словарь не удалось составить, переходим к озвучке и вопросам.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".opus") as tmp_voice:
            synthesize_japanese_voice(state.japanese_text, tmp_voice.name)
            with Path(tmp_voice.name).open("rb") as f:
                await update.message.reply_voice(
                    voice=InputFile(f), caption="Озвучка японского перевода"
                )
            Path(tmp_voice.name).unlink(missing_ok=True)

        state.logic_questions = generate_logic_questions(state.japanese_text)

        if state.vocab_questions:
            await update.message.reply_text("Начинаем тест по словам.")
            await run_vocab_question(update, state)
        else:
            state.phase = "logic_quiz"
            await update.message.reply_text("Переходим к вопросам на логику и расчет.")
            await run_vocab_question(update, state)
    except Exception as exc:
        logger.exception("Failed to process user text: %s", exc)
        state.phase = "idle"
        await update.message.reply_text(
            "Не удалось обработать текст из-за ошибки API/сети. "
            "Попробуй еще раз или проверь /health."
        )


def main() -> None:
    request_kwargs: Dict[str, Any] = {
        "connect_timeout": TELEGRAM_CONNECT_TIMEOUT,
        "read_timeout": TELEGRAM_READ_TIMEOUT,
        "write_timeout": TELEGRAM_WRITE_TIMEOUT,
        "pool_timeout": TELEGRAM_POOL_TIMEOUT,
    }
    if TELEGRAM_PROXY_URL:
        request_kwargs["proxy"] = TELEGRAM_PROXY_URL
        logger.info("Telegram proxy is enabled.")

    request = HTTPXRequest(**request_kwargs)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    # Do not fail startup if OpenAI is temporarily unavailable.
    # Connectivity can be checked via /health command.
    # check_openai_api()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text))
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            bootstrap_retries=TELEGRAM_BOOTSTRAP_RETRIES,
        )
    except (NetworkError, TimedOut) as exc:
        logger.error(
            "Не удалось подключиться к Telegram API: %s. "
            "Проверь internet/proxy и значение TELEGRAM_PROXY_URL в .env.",
            exc,
        )
        raise


if __name__ == "__main__":
    main()
