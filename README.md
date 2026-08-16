# Telegram Screen Monitor Bot

Простой Telegram-бот для удалённого просмотра экрана Windows без собственного сервера, домена, reverse proxy или VPN.

Бот запускается **на Windows-компьютере, экран которого нужно показывать**. Он делает скриншот через `mss` и каждые N секунд обновляет одно Telegram-сообщение у разрешённого пользователя.

> Используйте только на компьютерах, которыми вы владеете или на мониторинг которых у вас есть явное разрешение.

## Возможности

- захват одного монитора или всех мониторов сразу;
- JPEG с регулируемым качеством, включая 4K без уменьшения;
- обновление одного сообщения вместо спама новыми сообщениями;
- доступ только по Telegram user ID;
- несколько разрешённых пользователей;
- восстановление `message_id` после перезапуска через локальный `state.json`;
- команды `/start`, `/screen`, `/status`, `/stop`;
- автоматическое восстановление после временных сетевых ошибок;
- никаких входящих портов и публичного web-сервера.

## Как это работает

```text
Windows PC
   │
   ├─ mss -> screenshot
   ├─ Pillow -> JPEG
   │
   └─ Telegram Bot API (HTTPS)
                │
                ▼
          Telegram chat
          [Live screen]
          сообщение обновляется
          каждые 10 секунд
```

## 1. Создание Telegram-бота

1. Откройте `@BotFather` в Telegram.
2. Выполните `/newbot`.
3. Задайте имя и username.
4. Скопируйте полученный bot token.

Токен выглядит примерно так:

```text
1234567890:AA...
```

Никому его не отправляйте и не коммитьте `.env` в Git.

## 2. Узнать Telegram user ID зрителя

Самый простой способ — написать боту вроде `@userinfobot` и посмотреть свой числовой `Id`.

Пример:

```text
123456789
```

Именно этот ID нужно поместить в `ALLOWED_USER_IDS`. Бот отклоняет команды от остальных пользователей.

## 3. Установка на Windows

Установите Python 3.11+ и в PowerShell выполните:

```powershell
git clone https://github.com/Saveliq/tg-screen-monitor-bot.git
cd tg-screen-monitor-bot

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 4. Настройка

Скопируйте `.env.example` в `.env`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Пример `.env`:

```dotenv
BOT_TOKEN=1234567890:YOUR_TOKEN
ALLOWED_USER_IDS=123456789
SCREEN_INTERVAL=10
SCREEN_MONITOR=0
SCREEN_JPEG_QUALITY=92
SCREEN_MAX_WIDTH=0
STATE_FILE=state.json
```

### Параметры

`BOT_TOKEN` — токен от BotFather.

`ALLOWED_USER_IDS` — числовые Telegram user ID, которым разрешён просмотр. Несколько ID:

```dotenv
ALLOWED_USER_IDS=123456789,987654321
```

`SCREEN_INTERVAL` — интервал обновления в секундах. По умолчанию `10`, минимум `3`.

`SCREEN_MONITOR`:

- `0` — все мониторы как один общий скриншот;
- `1` — первый монитор;
- `2` — второй монитор и т.д.

`SCREEN_JPEG_QUALITY` — качество JPEG от 30 до 95. Для текста рекомендуется `90-95`.

`SCREEN_MAX_WIDTH`:

- `0` — не уменьшать картинку;
- `2560` — уменьшать только если ширина больше 2560 px;
- `1920` — экономный режим.

Для максимального качества:

```dotenv
SCREEN_JPEG_QUALITY=95
SCREEN_MAX_WIDTH=0
```

## 5. Запуск

```powershell
.\.venv\Scripts\python.exe .\run.py
```

В консоли появится примерно:

```text
Started @your_bot; monitors=2; interval=10s
```

Теперь разрешённый пользователь открывает бота и нажимает **Start** или пишет:

```text
/start
```

Бот отправит сообщение `Live screen`. Дальше именно это сообщение будет обновляться.

## Команды

- `/start` — включить просмотр в текущем чате;
- `/screen` — немедленно обновить скриншот;
- `/status` — состояние клиента;
- `/stop` — перестать автоматически обновлять экран в этом чате.

## Автозапуск Windows

Захват экрана должен выполняться в интерактивной пользовательской сессии Windows. Поэтому используйте **Task Scheduler** с `Run only when user is logged on`, а не Windows Service под Session 0.

Создайте задачу:

- Trigger: `At log on`;
- Program:

```text
C:\path\to\tg-screen-monitor-bot\.venv\Scripts\pythonw.exe
```

- Arguments:

```text
C:\path\to\tg-screen-monitor-bot\run.py
```

- Start in:

```text
C:\path\to\tg-screen-monitor-bot
```

`pythonw.exe` запускает приложение без постоянно открытого консольного окна.

Для первичной настройки сначала запускайте через `python.exe`, чтобы видеть ошибки в терминале.

## Безопасность

- `.env` добавлен в `.gitignore`;
- доступ ограничивается `ALLOWED_USER_IDS`;
- соединение с Telegram идёт по HTTPS;
- входящие порты на Windows или Linux не требуются;
- bot token даёт полный контроль над ботом — при утечке перевыпустите его через BotFather.

Важно: человек с доступом к Windows-профилю, где лежит `.env`, сможет прочитать bot token. Это обычная модель локального секрета для небольшого персонального приложения.

## Проверка

Быстрая проверка синтаксиса:

```powershell
.\.venv\Scripts\python.exe -m compileall bot run.py
```

Тесты:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```

## Почему без Docker

Контейнер Docker на Windows обычно не имеет прямого доступа к интерактивному пользовательскому desktop session. Для честного захвата экрана этот проект намеренно запускается как обычный Windows Python-процесс.
