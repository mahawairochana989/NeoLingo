"""
Проверка: доступен ли локальный прокси из .env (TELEGRAM_PROXY_URL).
Запуск: python check_proxy.py
"""
import os
import socket
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    url = os.getenv("TELEGRAM_PROXY_URL", "").strip()
    if not url:
        print("TELEGRAM_PROXY_URL пуст — бот идет в Telegram напрямую.")
        return

    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        print(f"Некорректный URL прокси: {url!r}")
        print("Примеры: http://127.0.0.1:7890  или  socks5://127.0.0.1:1080")
        return

    print(f"Проверка TCP до прокси {host}:{port} ...")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        print("OK: порт открыт, локальный прокси отвечает.")
    except OSError as exc:
        print(f"ОШИБКА: не удалось подключиться к {host}:{port}: {exc}")
        print(
            "Запусти VPN/Clash/V2Ray и сверь порт в настройках "
            "(HTTP и SOCKS — разные порты)."
        )


if __name__ == "__main__":
    main()
