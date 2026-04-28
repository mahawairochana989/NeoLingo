# Telegram-бот для изучения японского с ИИ

Бот принимает текст на любом языке и:

1. Переводит его на японский.
2. Делает словарь по всем смысловым словам (без частиц, глаголы в словарной форме).
3. Для словаря дает чтение на хирагане (для слов-катаканизмов чтение может быть пустым).
4. Проводит тест на ввод японских слов.
5. Начисляет звезды и баллы за правильные ответы.
6. Отправляет аудио с японским текстом.
7. Генерирует вопросы на логику/математику по содержанию текста и проверяет ответы.
8. В конце присылает карточку с ёдзидзюкуго.

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

1. Скопируй `.env.example` в `.env`.
2. Укажи:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`
   - (опционально) `OPENAI_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`
   - (при проблемах с сетью) `TELEGRAM_PROXY_URL`, например `http://127.0.0.1:10809`
   - (для автосинхронизации лидерборда) `RESULTS_API_URL`, `RESULTS_API_KEY`, `COURSE_DEFAULT_LESSON`

## Запуск

```bash
python bot.py
```

## Results API (автосинхронизация с лидербордом)

Запуск API локально:

```bash
uvicorn results_api:app --host 0.0.0.0 --port 8000
```

Эндпоинты:
- `GET /api/health`
- `GET /api/results`
- `POST /api/results` (при включенном `RESULTS_API_KEY` нужен заголовок `x-api-key`)

## Веб-лидерборд

Файлы: `leaderboard/`.

Локальный запуск:

```bash
python -m http.server 8891 --bind 0.0.0.0 --directory leaderboard
```

Чтобы лидерборд автоматически тянул данные из API:
1. Открой `leaderboard/config.js`
2. Укажи:
   - `window.NEOLINGO_API_URL = "https://<your-results-api>.up.railway.app"`
   - `window.NEOLINGO_API_KEY = "<key-if-required>"`

Бот запускается локально через long polling (сервер/хостинг не нужен).
Нужны только валидные ключи в `.env` и сетевой доступ до:
- `api.telegram.org`
- `api.openai.com`

Если `TELEGRAM_PROXY_URL` пустой, бот работает без прокси/VPN (при доступной сети).

## Если есть таймаут до Telegram

Если при старте появляется `telegram.error.TimedOut`, это проблема соединения с Telegram API.
Можно задать прокси и таймауты в `.env`:

```env
TELEGRAM_PROXY_URL=http://127.0.0.1:10809
TELEGRAM_CONNECT_TIMEOUT=30
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_WRITE_TIMEOUT=30
TELEGRAM_POOL_TIMEOUT=10
TELEGRAM_BOOTSTRAP_RETRIES=5
```

## Если `httpx.ConnectError: All connection attempts failed`

Такая ошибка чаще всего означает, что **до локального прокси не удается подключиться** (не тот порт, прокси выключен или указан неверный тип).

1. Убедись, что VPN/прокси-клиент **запущен** и порт совпадает с настройками приложения.
2. Проверь порт в PowerShell (подставь свой порт вместо `10809`):

```powershell
Test-NetConnection 127.0.0.1 -Port 10809
```

Если `TcpTestSucceeded : False`, на этом порту ничего не слушает — нужен другой порт из настроек клиента.

3. **HTTP и SOCKS — разные URL.** Если в клиенте указан SOCKS5-порт, в `.env` должно быть так:

```env
TELEGRAM_PROXY_URL=socks5://127.0.0.1:1080
```

Для HTTP-прокси (часто в Clash/V2Ray: «Mixed» или «HTTP») используй:

```env
TELEGRAM_PROXY_URL=http://127.0.0.1:7890
```

4. Если Telegram у тебя открывается **без** прокси, очисти строку:

```env
TELEGRAM_PROXY_URL=
```

После смены прокси переустанови зависимости (нужен SOCKS для `socks5://`):

```bash
pip install -r requirements.txt
```

## Команды

- `/start` или `/help` — инструкция
- `/score` — текущий счет
- `/reset` — сброс прогресса
- `/health` — проверка подключения OpenAI/прокси
