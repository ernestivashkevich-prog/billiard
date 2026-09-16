#!/usr/bin/env bash
# Ежедневный бэкап файла БД SQLite. Добавьте в cron, например:
# 0 3 * * * /path/to/billiard/scripts/backup.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_FILE="$PROJECT_DIR/data/billiard.db"
BACKUP_DIR="$PROJECT_DIR/data/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$BACKUP_DIR/billiard_${TIMESTAMP}.db"
    echo "Бэкап создан: $BACKUP_DIR/billiard_${TIMESTAMP}.db"
    # храним последние 30 бэкапов
    ls -1t "$BACKUP_DIR"/billiard_*.db | tail -n +31 | xargs -r rm --
else
    echo "Файл БД не найден: $DB_FILE" >&2
    exit 1
fi
