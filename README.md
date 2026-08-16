# Telegram Screen Monitor Bot

Система для удалённого просмотра скриншотов Windows через Telegram.

Архитектура разделена на две независимые части:

```text
Windows PC                          Linux / Portainer
┌────────────────────┐             ┌──────────────────────────┐
│ client/client.py   │             │ tg-screen-monitor-bot    │
│                    │ POST /upload│                          │
│ mss -> screenshot  ├────────────►│ HTTP receiver            │
│ Pillow -> JPEG     │             │ + Telegram bot           │
└────────────────────┘             └────────────┬─────────────┘
                                               │
                                               ▼
                                         Telegram chat
                                         [Live screen]
```

Windows-клиент **не содержит BOT_TOKEN и не общается с Telegram**. Он только делает скриншот и отправляет JPEG на Linux-сервер. Linux-сервис принимает кадр, сохраняет `latest.jpg` и обновляет одно сообщение `Live screen` в Telegram.

> Используйте только на компьютерах, которыми вы владеете или на мониторинг которых у вас есть явное разрешение.

## Возможности

- Windows-клиент запускается один раз и работает постоянно;
- скриншот по умолчанию каждые 10 секунд;
- один монитор или все мониторы;
- JPEG до качества 95 без принудительного уменьшения;
- автоматическая адаптация слишком больших изображений под ограничения Telegram;
- Linux-сервер разворачивается одним Stack в Portainer;
- Telegram-бот работает на Linux 24/7;
- `/start` включает просмотр;
- `/stop` останавливает обновление конкретному зрителю;
- `/screen` показывает последний сохранённый кадр;
- `/status` показывает online/offline Windows-клиента;
- несколько разрешённых Telegram-пользователей;
- состояние и последний JPEG переживают перезапуск контейнера;
- новые кадры заменяют картинку в одном Telegram-сообщении, а не спамят чат.

# 1. Создать Telegram-бота

В Telegram откройте `@BotFather`:

1. `/newbot`
2. задайте имя;
3. задайте username;
4. сохраните полученный `BOT_TOKEN`.

Пример:

```text
1234567890:AAExampleToken
```

## Узнать Telegram user ID

Нужен числовой ID человека, который будет смотреть скриншоты. Его можно узнать, например, через `@userinfobot`.

Пример:

```text
123456789
```

Несколько зрителей можно указать через запятую:

```text
123456789,987654321
```

# 2. Сгенерировать UPLOAD_TOKEN

Это отдельный секрет между Windows-клиентом и Linux-сервером.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Один и тот же `UPLOAD_TOKEN` должен быть установлен на сервере и Windows-клиенте.

# 3. Развернуть Linux-сервер через Portainer

Репозиторий:

```text
https://github.com/Saveliq/tg-screen-monitor-bot
```

В Portainer:

1. **Stacks** → **Add stack**.
2. Выберите **Repository / Git repository**.
3. Repository URL: `https://github.com/Saveliq/tg-screen-monitor-bot`.
4. Compose path: `docker-compose.yml`.
5. Добавьте Environment variables:

```text
BOT_TOKEN=токен_от_BotFather
UPLOAD_TOKEN=длинный_случайный_секрет
ALLOWED_USER_IDS=123456789
HTTP_PORT=8080
MAX_UPLOAD_BYTES=9500000
OFFLINE_AFTER_SECONDS=30
```

6. Нажмите **Deploy the stack**.

Portainer соберёт Docker image из `server/Dockerfile` и создаст named volume `screen-monitor-data`.

В volume хранятся:

```text
/data/latest.jpg
/data/latest.json
/data/state.json
```

# 4. Проверить Linux-сервер

После запуска:

```text
http://IP_СЕРВЕРА:8080/healthz
```

Нормальный ответ до первого кадра:

```json
{"ok": true, "has_frame": false, "last_frame_at": null, "viewers": 0}
```

Загрузка выполняется через:

```text
POST /upload
Authorization: Bearer UPLOAD_TOKEN
Content-Type: image/jpeg
```

Windows должен иметь сетевой доступ к серверу. Если `/upload` доступен через интернет, используйте HTTPS или VPN: обычный HTTP не шифрует скриншоты.

# 5. Установить Windows-клиент

```powershell
git clone https://github.com/Saveliq/tg-screen-monitor-bot.git
cd tg-screen-monitor-bot\client
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Пример `client/.env`:

```dotenv
SERVER_URL=http://192.168.1.50:8080
UPLOAD_TOKEN=тот_же_секрет_что_в_Portainer
SCREEN_INTERVAL=10
SCREEN_MONITOR=0
SCREEN_JPEG_QUALITY=95
SCREEN_MAX_WIDTH=0
REQUEST_TIMEOUT=30
```

`SCREEN_MONITOR`: `0` — все мониторы, `1` — первый, `2` — второй.

`SCREEN_MAX_WIDTH=0` отключает предварительное уменьшение разрешения.

# 6. Запустить Windows-клиент

```powershell
.\.venv\Scripts\python.exe .\client.py
```

Клиент запускается один раз и работает постоянно. При временной ошибке сети процесс не завершается, а продолжает следующие попытки.

# 7. Включить просмотр в Telegram

Разрешённый пользователь пишет боту:

```text
/start
```

После появления кадра бот создаёт `Live screen`. Каждый следующий upload заменяет фотографию в том же сообщении.

Команды:

- `/start` — включить автоматические обновления;
- `/stop` — выключить их для текущего чата;
- `/screen` — показать последний сохранённый кадр;
- `/status` — online/offline клиента, возраст, размер и разрешение последнего кадра.

# 8. Автозапуск Windows

Используйте Windows Task Scheduler и **Run only when user is logged on**, потому что захват desktop должен выполняться в интерактивной пользовательской сессии.

Program:

```text
C:\ScreenMonitor\client\.venv\Scripts\pythonw.exe
```

Arguments:

```text
C:\ScreenMonitor\client\client.py
```

Start in:

```text
C:\ScreenMonitor\client
```

Для первичной диагностики запускайте через `python.exe`, чтобы видеть логи.

# Безопасность

На Windows хранится только `SERVER_URL` и `UPLOAD_TOKEN`. `BOT_TOKEN` находится только на Linux. Доступ в Telegram ограничен `ALLOWED_USER_IDS`.

`.env` файлы исключены из Git.
