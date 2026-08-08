# TG Shop

SaaS-платформа для запуска нескольких Telegram-ботов магазинов с одного сервера.
Клиент подключает своего бота (через bot token), получает онбординг, триал,
подписки и приём платежей.

**Стек:** Python 3.12, aiogram 3.22, FastAPI, SQLAlchemy 2.0 (async),
PostgreSQL 16, React/Next.js 16 (admin), Caddy 2, Docker Compose.

---

## Содержание

- [Быстрый старт (локально)](#быстрый-старт-локально)
- [Деплой на VPS](#деплой-на-vps)
- [Переменные окружения](#переменные-окружения)
- [Бэкапы и восстановление](#бэкапы-и-восстановление)
- [Архитектура](#архитектура)
- [Чек-лист запуска в production](#чек-лист-запуска-в-production)

---

## Быстрый старт (локально)

### Требования

- Python 3.12+
- Telegram bot token (от [@BotFather](https://t.me/BotFather))

### Установка

```bash
git clone https://github.com/YuryMitichev/tg_shop.git
cd tg_shop

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
```

### Настройка окружения

```bash
cp .env.example .env
```

Откройте `.env` и заполните обязательные значения:

| Переменная       | Как получить                                                            |
| ---------------- | ----------------------------------------------------------------------- |
| `BOT_TOKEN`      | [@BotFather](https://t.me/BotFather) → `/newbot`                        |
| `JWT_SECRET`     | `python -c "import secrets; print(secrets.token_hex(32))"`              |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### Запуск бота

```bash
python run.py
```

### Запуск тестов

```bash
python -m pytest --tb=short -q
```

### Запуск админ-панели (отдельно)

```bash
cd admin
npm install
npm run dev
```

---

## Деплой на VPS

### Требования к серверу

- Linux VPS с публичным IP
- Docker + Docker Compose
- Домен с A-записями, указывающими на IP сервера:
  - `@` → IP сервера
  - `admin` → IP сервера (для админ-панели)

### Шаг 1. Подготовка сервера

```bash
ssh root@<VPS_IP>

# Установить Docker (если не установлен)
curl -fsSL https://get.docker.com | sh

git clone https://github.com/YuryMitichev/tg_shop.git
cd tg_shop
```

### Шаг 2. Настройка `.env`

```bash
cp .env.example .env
nano .env
```

Заполните обязательные переменные (см. таблицу выше). Также задайте:

- `POSTGRES_PASSWORD` — надёжный пароль для БД
- `DOMAIN` — ваш домен без протокола
- `APP_BASE_URL` — `https://<домен>`
- `ADMIN_PANEL_URL` — `https://admin.<домен>` (необязательно)

### Шаг 3. Запуск

```bash
docker compose up -d --build
```

Caddy автоматически получит SSL-сертификаты (Let's Encrypt) при первом запуске.

### Проверка

```bash
docker compose ps            # все контейнеры healthy
curl https://<домен>/health  # {"status":"ok"}
```

### Логи

```bash
docker compose logs -f bot
docker compose logs -f caddy
```

### Обновление

```bash
git pull
docker compose up -d --build
docker image prune -f
```

> Автоматический деплой через GitHub Actions настраивается в репозитории
> (см. `.github/workflows/deploy.yml`). Нужны секреты `VPS_HOST` и `VPS_SSH_KEY`.

---

## Переменные окружения

Полный список — в [`.env.example`](.env.example). Кратко:

| Категория         | Переменные                                                                  |
| ----------------- | --------------------------------------------------------------------------- |
| Telegram          | `BOT_TOKEN`, `PLATFORM_BOT_TOKEN`, `MANAGER_CHAT_ID`, `ADMIN_IDS`, `SUPER_ADMIN_IDS`, `BOT_PROXY` |
| База данных       | `DATABASE_URL`, `POSTGRES_PASSWORD`                                          |
| Приложение        | `DEBUG`, `SHOP_NAME`, `DOMAIN`, `APP_BASE_URL`, `ADMIN_PANEL_URL`            |
| Аутентификация    | `JWT_SECRET`, `CORS_ORIGINS`, `ENCRYPTION_KEY`                               |
| Платежи           | `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `TINKOFF_TERMINAL_KEY`, `TINKOFF_PASSWORD`, `PAYMENT_CARD_NUMBER`, `PAYMENT_RECIPIENT_NAME` |
| Мониторинг        | `SENTRY_DSN`                                                                |

---

## Бэкапы и восстановление

Автоматические бэкапы БД выполняются контейнером `tg_shop_backup` каждый день в 03:00.
Бэкапы хранятся в volume `backup_data` с ротацией (7 последних дней).

Подробности восстановления — в [`docs/backup-restore.md`](docs/backup-restore.md).

---

## Архитектура

```
                ┌──────────────────────────────────────────┐
                │                   Caddy                   │
                │   (TLS, reverse proxy: 80/443 → bot/admin)│
                └──────────┬───────────────────┬────────────┘
                           │                   │
                   ┌───────▼───────┐  ┌────────▼────────┐
                   │   bot (FastAPI│  │  admin (Next.js)│
                   │   + aiogram)  │  │                 │
                   └───────┬───────┘  └────────┬────────┘
                           │                   │
                           └────────┬──────────┘
                                    │
                            ┌───────▼───────┐
                            │  PostgreSQL   │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │  backup (cron)│
                            └───────────────┘
```

Контейнеры:

| Контейнер        | Назначение                              |
| ---------------- | --------------------------------------- |
| `tg_shop_db`     | PostgreSQL 16                           |
| `tg_shop_bot`    | FastAPI + aiogram бот                   |
| `tg_shop_admin`  | Next.js админ-панель                    |
| `tg_shop_caddy`  | Caddy reverse proxy + автоматический TLS|
| `tg_shop_backup` | Cron-контейнер для ежедневных бэкапов   |

---

## Чек-лист запуска в production

- [ ] Домен настроен: A-записи `@` и `admin` → IP сервера
- [ ] `.env` заполнен: `BOT_TOKEN`, `JWT_SECRET`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD`
- [ ] `DOMAIN` и `APP_BASE_URL` указывают на ваш домен
- [ ] `docker compose up -d --build` — все контейнеры `healthy`
- [ ] `https://<домен>/health` возвращает `{"status":"ok"}`
- [ ] Админ-панель открывается по `https://admin.<домен>` (если настроено)
- [ ] SSL-сертификат активен (Caddy получил его автоматически)
- [ ] Бот отвечает в Telegram
- [ ] (Опц.) `SENTRY_DSN` задан — ошибки видны в Sentry
- [ ] (Опц.) `YOOKASSA_SHOP_ID` + `YOOKASSA_SECRET_KEY` — оплата подписок работает
- [ ] (Опц.) GitHub Secrets `VPS_HOST` + `VPS_SSH_KEY` — авто-деплой активен
