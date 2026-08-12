"""SQLite database setup for manager state."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def initialize_database(path: str | Path) -> sqlite3.Connection:
    """Open and initialize the manager database at *path*."""
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            options_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            progress_json TEXT
        )
    ''')
    columns = {row['name'] for row in connection.execute('PRAGMA table_info(jobs)')}
    if 'progress_json' not in columns:
        connection.execute('ALTER TABLE jobs ADD COLUMN progress_json TEXT')
    connection.execute('CREATE INDEX IF NOT EXISTS jobs_created_at_idx ON jobs (created_at DESC, id ASC)')
    connection.commit()
    return connection
