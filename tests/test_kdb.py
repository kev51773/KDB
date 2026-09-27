import os
import sqlite3
import pytest
from pathlib import Path
import app.db_store as db_store
import app.db_engine as db_engine

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    orig_conn = db_store.CONNECTIONS_PATH
    orig_bm = db_store.BOOKMARKS_PATH
    orig_hist = db_store.HISTORY_PATH

    db_store.CONNECTIONS_PATH = tmp_path / "test_kdb_connections.json"
    db_store.BOOKMARKS_PATH = tmp_path / "test_kdb_bookmarks.json"
    db_store.HISTORY_PATH = tmp_path / "test_kdb_history.json"
    db_store.init_store_db()
    yield
    db_store.CONNECTIONS_PATH = orig_conn
    db_store.BOOKMARKS_PATH = orig_bm
    db_store.HISTORY_PATH = orig_hist

def test_db_store_connections():
    initial_count = len(db_store.list_connections())
    conn_id = db_store.save_connection({
        "name": "Test SQLite",
        "db_type": "sqlite",
        "database": ":memory:"
    })
    assert conn_id > 0

    conns = db_store.list_connections()
    assert len(conns) == initial_count + 1
    assert any(c["name"] == "Test SQLite" for c in conns)

    detail = db_store.get_connection(conn_id)
    assert detail["db_type"] == "sqlite"

    db_store.delete_connection(conn_id)
    assert len(db_store.list_connections()) == initial_count

def test_db_store_bookmarks_and_groups():
    groups = db_store.list_bookmark_groups()
    assert len(groups) == 0  # initially empty

    group_id = db_store.save_bookmark_group({
        "name": "QA Smoke Tests",
        "color": "#10B981",
        "connection_id": 10
    })
    assert group_id > 0

    group2_id = db_store.save_bookmark_group({
        "name": "Prod Tests",
        "color": "#EF4444",
        "connection_id": 20
    })
    assert group2_id > 0

    groups_conn10 = db_store.list_bookmark_groups(connection_id=10)
    assert len(groups_conn10) == 1
    assert groups_conn10[0]["id"] == group_id

    bm_id = db_store.save_bookmark({
        "group_id": group_id,
        "title": "Check Active Users",
        "sql_query": "SELECT * FROM users WHERE status = 'active';",
        "notes": "Must return > 0 rows"
    })
    assert bm_id > 0

    bookmarks = db_store.list_bookmarks(group_id=group_id, connection_id=10)
    assert len(bookmarks) == 1
    assert bookmarks[0]["title"] == "Check Active Users"
    assert bookmarks[0]["connection_id"] == 10

def test_export_and_import_bookmarks():
    g_id = db_store.save_bookmark_group({"name": "Export Group", "connection_id": 100})
    bm_id = db_store.save_bookmark({"group_id": g_id, "title": "Export BM", "connection_id": 100})

    exported = db_store.export_bookmarks_data()
    assert "connection_id" not in exported["groups"][0]
    assert "connection_id" not in exported["bookmarks"][0]

    # Import into target connection 200
    db_store.import_bookmarks_data(exported, target_connection_id=200)

    imported_groups = db_store.list_bookmark_groups(connection_id=200)
    imported_bms = db_store.list_bookmarks(connection_id=200)

    assert any(g["name"] == "Export Group" for g in imported_groups)
    assert any(b["title"] == "Export BM" for b in imported_bms)

def test_delete_bookmark_group_cascade():
    parent_g = db_store.save_bookmark_group({"name": "Parent Folder"})
    child_g = db_store.save_bookmark_group({"name": "Child Folder", "parent_id": parent_g})
    bm_id = db_store.save_bookmark({"group_id": child_g, "title": "Child Bookmark"})

    # Delete parent folder
    db_store.delete_bookmark_group(parent_g)

    groups = db_store.list_bookmark_groups()
    bms = db_store.list_bookmarks()
    assert not any(g["id"] in (parent_g, child_g) for g in groups)
    assert not any(b["id"] == bm_id for b in bms)

def test_unencrypted_sqlite_fails_with_password(tmp_path):
    sample_db_path = tmp_path / "plain.db"
    conn = sqlite3.connect(sample_db_path)
    conn.execute("CREATE TABLE t (id INT);")
    conn.commit()
    conn.close()

    config = {
        "db_type": "sqlite",
        "database": str(sample_db_path),
        "password": "wrong_key_for_plain_db"
    }
    ok, msg = db_engine.test_connection(config)
    assert ok is False
    assert "database" in msg.lower() or "file" in msg.lower()

def test_sqlite_empty_database_path_fails():
    config = {
        "db_type": "sqlite",
        "database": ""
    }
    ok, msg = db_engine.test_connection(config)
    assert ok is False
    assert "Database File Path is required" in msg

def test_sqlite_engine_execution(tmp_path):
    # Create sample sqlite DB
    sample_db_path = tmp_path / "sample.db"
    conn = sqlite3.connect(sample_db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);")
    conn.execute("INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com');")
    conn.execute("INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com');")
    conn.commit()
    conn.close()

    config = {
        "db_type": "sqlite",
        "database": str(sample_db_path)
    }

    # Test connection
    ok, msg = db_engine.test_connection(config)
    assert ok is True

    # Test schema inspection
    schema = db_engine.inspect_schema(config)
    assert len(schema["tables"]) == 1
    assert schema["tables"][0]["name"] == "users"
    assert "id" in schema["tables"][0]["primary_keys"]

    # Test query execution
    res = db_engine.execute_raw_query(config, "SELECT * FROM users ORDER BY id ASC")
    assert res["status"] == "success"
    assert res["row_count"] == 2
    assert res["rows"][0]["name"] == "Alice"

    # Test cell update
    update_res = db_engine.update_cell_value(
        config=config,
        table_name="users",
        pk_col="id",
        pk_val=1,
        col_name="name",
        new_val="Alice Updated"
    )
    assert update_res["status"] == "success"
    assert update_res["rows_affected"] == 1

    # Verify update in DB
    verify_res = db_engine.execute_raw_query(config, "SELECT name FROM users WHERE id = 1")
    assert verify_res["rows"][0]["name"] == "Alice Updated"

def test_read_only_mode(tmp_path):
    sample_db_path = tmp_path / "ro_sample.db"
    conn = sqlite3.connect(sample_db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO items (name) VALUES ('Test Item');")
    conn.commit()
    conn.close()

    conn_id = db_store.save_connection({
        "name": "RO SQLite DB",
        "db_type": "sqlite",
        "database": str(sample_db_path),
        "is_read_only": True
    })

    conn_config = db_store.get_connection(conn_id)
    assert conn_config["is_read_only"] == 1

    # Query execution check
    import app.routes.query as query_route
    req_select = query_route.QueryRequest(connection_id=conn_id, sql_query="SELECT * FROM items")
    res_select = query_route.execute_query(req_select)
    assert res_select["status"] == "success"

    # Write query check -> should raise 403
    from fastapi import HTTPException
    req_write = query_route.QueryRequest(connection_id=conn_id, sql_query="UPDATE items SET name = 'Hacked'")
    with pytest.raises(HTTPException) as exc_info:
        query_route.execute_query(req_write)
    assert exc_info.value.status_code == 403

    # Cell edit check -> should raise 403
    import app.routes.edit as edit_route
    req_edit = edit_route.CellUpdateRequest(
        connection_id=conn_id,
        table_name="items",
        pk_column="id",
        pk_value=1,
        column_name="name",
        new_value="Cell Hacked"
    )
    with pytest.raises(HTTPException) as exc_info_edit:
        edit_route.update_cell(req_edit)
    assert exc_info_edit.value.status_code == 403

    # Autocomplete check -> should NOT contain UPDATE or INSERT
    import app.sql_completer as sql_completer
    ro_schema = {"tables": [{"name": "items", "columns": [{"name": "id"}, {"name": "name"}]}], "is_read_only": True}
    res_ac = sql_completer.get_sql_completions("u", 1, ro_schema)
    kw_texts = [item["text"] for item in res_ac if item["type"] == "keyword"]
    assert "UPDATE" not in kw_texts

