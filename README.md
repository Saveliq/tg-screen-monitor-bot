# Telegram Screen Monitor Bot

Система для просмотра скриншотов Windows через Telegram.

Архитектура:

```text
Windows PC
  client/client.py
       |
       | POST /upload + Bearer UPLOAD_TOKEN
       v
Linux / Portainer
  tg-screen-monitor-bot ---- SOCKS5 ----> Xray ---- VLESS ----> Telegram API
       |
       +--> /data/latest.jpg
       +--> Telegram Live screen
```

Windows-клиент не знает `BOT_TOKEN` и не подключается к Telegram. Он только делает скриншоты и отправляет JPEG на Linux. На Linux постоянно работают HTTP receiver и Telegram-бот. Для доступа Linux-сервера к Telegram используется Xray/VLESS, по той же схеме, что в `Saveliq/tg-voice-journal-bot`.

> Используйте только на компьютерах, которыми вы владеете или на мониторинг которых у вас есть разрешение.

## Что умеет

- Windows-клиент запускается один раз и работает постоянно;
- делает скриншот всех мониторов или выбранного монитора;
- регулируемые JPEG quality и максимальная ширина;
- повторяет отправку после сетевых ошибок;
- Linux разворачивается одним Stack в Portainer;
- `xray-config` генерирует Xray-конфиг из `VLESS_URL`;
- `proxy` поднимает SOCKS5 на `proxy:1080`;
- Telegram-бот ходит к Telegram API только через `socks5://proxy:1080`;
- каждый новый кадр заменяет фотографию в одном сообщении `Live screen`;
- `/start`, `/stop`, `/screen`, `/status`;
- разрешённые Telegram users задаются через `ALLOWED_USER_IDS`;
- последний кадр и state сохраняются в Docker volume.

## 1. Создать Telegram-бота

В `@BotFather` выполните `/newbot` и сохраните токен:

```text
BOT_TOKEN=1234567890:AA...
```

## 2. Узнать Telegram user ID

Нужен числовой ID зрителя. Например:

```text
123456789
```

Несколько пользователей:

```text
123456789,987654321
```

## 3. Создать UPLOAD_TOKEN

Это отдельный секрет между Windows и Linux.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Один и тот же токен указывается в Portainer и `client/.env`.

## 4. Подготовить VLESS_URL

Используйте рабочую VLESS-ссылку, которую вы уже применяете для Xray. Поддерживаются используемые генератором варианты `tcp`, `ws`, `grpc`, `xhttp`, а также `tls` и `reality`.

Пример формата:

```text
vless://UUID@host.example:443?security=reality&type=tcp&sni=example.com&fp=chrome&pbk=PUBLIC_KEY&sid=SHORT_ID#screen-bot
```

Не коммитьте настоящую VLESS URL в GitHub.

## 5. Развернуть Stack в Portainer

Repository:

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
VLESS_URL=ваша_полная_vless_ссылка
HTTP_PORT=8080
MAX_UPLOAD_BYTES=9500000
OFFLINE_AFTER_SECONDS=30
```

6. Нажмите **Deploy the stack**.

Stack создаёт три сервиса:

```text
xray-config
proxy
tg-screen-monitor-bot
```

### Что делает каждый контейнер

`xray-config` — одноразовый init-контейнер. Читает `VLESS_URL`, создаёт `/xray-config/config.json` и завершается с кодом 0.

`proxy` — `teddysun/xray:latest`. Читает созданный config и поднимает SOCKS5 внутри Docker-сети на `proxy:1080`.

`tg-screen-monitor-bot` — принимает screenshots на `/upload` и запускает aiogram polling. Compose автоматически задаёт ему:

```text
PROXY_URL=socks5://proxy:1080
```

Поэтому bot token/API запросы к Telegram проходят через Xray. Внешне порт SOCKS5 не публикуется.

## 6. Проверить сервер

После старта откройте:

```text
http://SERVER_IP:8080/healthz
```

До первого кадра ожидается примерно:

```json
{"ok": true, "has_frame": false, "last_frame_at": null, "viewers": 0}
```

В Portainer проверьте контейнеры:

```text
xray-config             exited (0)
proxy                   running
tg-screen-monitor-bot   running / healthy
```

В логах `xray-config` должно быть сообщение вида:

```text
Config written to /xray-config/config.json (...)
```

В логах бота:

```text
Telegram proxy: socks5://proxy:1080
Telegram bot @your_bot started
Upload API listening on http://0.0.0.0:8080/upload
```

Если `xray-config` завершается с ошибкой, в первую очередь проверьте `VLESS_URL`.

## 7. Windows-клиент

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
UPLOAD_TOKEN=ТОТ_ЖЕ_TOKEN_ЧТО_В_PORTAINER
SCREEN_INTERVAL=10
SCREEN_MONITOR=0
SCREEN_JPEG_QUALITY=95
SCREEN_MAX_WIDTH=0
REQUEST_TIMEOUT=30
```

`SCREEN_MONITOR=0` — все мониторы. `1` — первый, `2` — второй и т.д.

`SCREEN_MAX_WIDTH=0` — не уменьшать разрешение заранее.

Запуск:

```powershell
.\.venv\Scripts\python.exe .\client.py
```

Клиент один раз запускается и дальше постоянно выполняет:

```text
capture -> JPEG -> POST /upload -> sleep -> repeat
```

При временной ошибке сети процесс не завершается.

## 8. Telegram

Разрешённый пользователь пишет боту:

```text
/start
```

После получения кадра бот создаёт `Live screen`. Следующие uploads обновляют фото в этом же сообщении.

Команды:

```text
/start   включить просмотр
/stop    выключить автообновление для этого чата
/screen  показать последний сохранённый кадр
/status  показать состояние Windows-клиента
```

`/status` считает клиента offline, если новый кадр не приходил дольше `OFFLINE_AFTER_SECONDS`.

## 9. Проверить upload вручную

PowerShell:

```powershell
curl.exe `
  -X POST `
  -H "Authorization: Bearer ВАШ_UPLOAD_TOKEN" `
  -H "Content-Type: image/jpeg" `
  --data-binary "@C:\Temp\test.jpg" `
  "http://SERVER_IP:8080/upload"
```

## 10. Автозапуск Windows

Для захвата desktop используйте Task Scheduler с **Run only when user is logged on**.

Program:

```text
C:\path\to\tg-screen-monitor-bot\client\.venv\Scripts\python.exe
```

Arguments:

```text
C:\path\to\tg-screen-monitor-bot\client\client.py
```

Start in:

```text
C:\path\to\tg-screen-monitor-bot\client
```

## Безопасность

`UPLOAD_TOKEN`, `BOT_TOKEN` и `VLESS_URL` являются секретами. Храните их в Environment variables Portainer/локальном `.env`, а не в Git.

Если Windows отправляет screenshots через публичный интернет напрямую на `http://SERVER_IP:8080`, содержимое screenshot и upload token не шифруются транспортом. Для публичного маршрута используйте HTTPS или VPN. Xray в этом Stack защищает/обеспечивает именно исходящий доступ Linux-бота к Telegram, а не Windows → `/upload`.
