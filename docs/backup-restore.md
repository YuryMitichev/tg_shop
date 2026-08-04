# Восстановление БД из бэкапа

## Бэкапы

Контейнер `tg_shop_backup` автоматически создаёт бэкапы каждый день в 03:00:
- **Дневные:** `/backups/daily/` — хранятся 7 штук
- **Недельные** (по воскресеньям): `/backups/weekly/` — хранятся 4 штуки

Формат: `tg_shop_YYYYMMDD_HHMMSS.sql.gz` (gzip-сжатый SQL дамп)

## Восстановление

### Способ 1: Через docker exec

```bash
# Посмотреть список бэкапов
docker exec tg_shop_backup ls -lh /backups/daily/

# Восстановить из файла (замените имя файла)
gunzip -c /backups/daily/tg_shop_20250115_030000.sql.gz | \
    docker exec -i tg_shop_db psql -U tg_shop -d tg_shop
```

### Способ 2: Копировать файл на хост, затем восстановить

```bash
# Скопировать бэкап из контейнера
docker cp tg_shop_backup:/backups/daily/tg_shop_20250115_030000.sql.gz /tmp/

# Восстановить
gunzip -c /tmp/tg_shop_20250115_030000.sql.gz | \
    docker exec -i tg_shop_db psql -U tg_shop -d tg_shop
```

## Ручной бэкап

```bash
docker exec tg_shop_backup pg_dump -h postgres -U tg_shop tg_shop \
    --no-owner --no-privileges | gzip > /tmp/manual_backup.sql.gz
```
