# Миграции БД

Для старта на SQLite отдельный миграционный инструмент не требуется: при
запуске бот сам создаёт все таблицы (`models.db.init_db()` вызывает
`Base.metadata.create_all`), если их ещё нет.

Схема БД описана в `models/models.py` (`User`, `Match`, `RatingHistory`).

## Переход на Postgres

Если позже понадобится перейти на Postgres (или вносить изменения в схему
без потери данных на проде), добавьте Alembic:

```bash
pip install alembic
alembic init migrations/alembic
```

и настройте `alembic/env.py` на использование `models.models.Base.metadata`
как `target_metadata`, а строку подключения — брать из `DATABASE_URL`
(см. `bot/config.py`). Дальше обычный цикл:

```bash
alembic revision --autogenerate -m "описание изменений"
alembic upgrade head
```
