# KDB - QA Database Management Tool

A lightweight, modern web-based database client and query execution tool built for QA engineers and developers. Supports SQLite, PostgreSQL, MySQL, and MSSQL.

## Features

- **Connection Manager**: Manage saved database connection profiles with live search, custom DB type parameters, and Master-Detail configuration.
- **SQLite File Browser**: Easy local file selection for SQLite `.db` / `.sqlite` files.
- **Schema Explorer**: Interactive table tree with columns, types, and primary key indicators (`🔑`).
- **Interactive Data Grid**: Tabulator grid with sorting, filtering, and direct inline cell editing.
- **Safety Read-Only Mode**: Disable cell editing and write queries (`UPDATE`, `INSERT`, `DELETE`) for production/QA safety.
- **Query Bookmarks**: Organizable query folders with tag filtering, connection-specific scoping, and JSON import/export.
- **Query History**: Automatically tracks executed queries, execution times, and row counts (last 500 queries).

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Application
```bash
python run.py
```
Open your browser at `http://127.0.0.1:8000`.

### 3. Running Unit Tests
```bash
python -m pytest
```

## Project Structure

```
KDB/
├── app/
│   ├── main.py           # FastAPI application entry
│   ├── db_engine.py      # Multi-database execution engine
│   ├── db_store.py       # JSON storage manager
│   ├── routes/           # API endpoints (connections, query, schema, bookmarks, edit)
│   └── static/           # Web UI frontend (index.html, app.js, style.css)
├── sample_qa.db          # Sample QA SQLite database
├── create_sample_db.py   # Utility script to re-generate sample database
├── run.py                # App launcher
└── tests/                # Pytest test suite
```
