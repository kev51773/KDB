import time
from typing import Dict, List, Any, Tuple, Optional
from sqlalchemy import create_engine, inspect, text, Table, MetaData, Column
from sqlalchemy.engine import Engine
from urllib.parse import quote_plus

def build_connection_url(config: Dict[str, Any]) -> str:
    db_type = config.get("db_type", "").lower()
    database = config.get("database", "")
    username = config.get("username", "")
    password = config.get("password", "")
    host = config.get("host", "localhost")
    port = config.get("port")
    extra = config.get("extra_params", "")

    pass_encoded = quote_plus(password) if password else ""
    user_part = f"{username}:{pass_encoded}@" if username else ""

    if db_type == "sqlite":
        # Handle SQLite file path
        if not database:
            return "sqlite:///:memory:"
        return f"sqlite:///{database}"
    
    elif db_type in ("postgresql", "postgres"):
        port_part = f":{port}" if port else ":5432"
        extra_part = f"?{extra}" if extra else ""
        return f"postgresql+psycopg2://{user_part}{host}{port_part}/{database}{extra_part}"
    
    elif db_type == "mysql":
        port_part = f":{port}" if port else ":3306"
        extra_part = f"?{extra}" if extra else ""
        return f"mysql+pymysql://{user_part}{host}{port_part}/{database}{extra_part}"
    
    elif db_type in ("mssql", "sqlserver"):
        # Try pymssql driver first as it has bundled FreeTDS
        port_part = f":{port}" if port else ":1433"
        extra_part = f"?{extra}" if extra else ""
        return f"mssql+pymssql://{user_part}{host}{port_part}/{database}{extra_part}"
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")

def get_engine(config: Dict[str, Any]) -> Engine:
    db_type = config.get("db_type", "").lower()
    database = config.get("database", "")
    password = config.get("password", "")

    if db_type == "sqlite" and password:
        def sqlite_cipher_creator():
            try:
                import sqlcipher3 as sqlite3_driver
            except ImportError:
                try:
                    from pysqlcipher3 import dbapi2 as sqlite3_driver
                except ImportError:
                    raise RuntimeError(
                        "SQLCipher driver (sqlcipher3 or pysqlcipher3) is required to open encrypted SQLite databases. "
                        "Install via 'pip install sqlcipher3'"
                    )
            db_path = database if database else ":memory:"
            conn = sqlite3_driver.connect(db_path)
            escaped_pass = password.replace("'", "''")
            conn.execute(f"PRAGMA key = '{escaped_pass}';")
            return conn

        return create_engine("sqlite://", creator=sqlite_cipher_creator, pool_pre_ping=True)

    url = build_connection_url(config)
    connect_args = {}
    if db_type in ("postgresql", "postgres"):
        connect_args["connect_timeout"] = 5
    elif db_type == "mysql":
        connect_args["connect_timeout"] = 5

    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

def test_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        db_type = config.get("db_type", "").lower()
        database = (config.get("database") or "").strip()
        if db_type == "sqlite" and not database:
            return False, "Database File Path is required for SQLite connections."

        engine = get_engine(config)
        test_stmt = "SELECT count(*) FROM sqlite_master" if db_type == "sqlite" else "SELECT 1"
        with engine.connect() as conn:
            conn.execute(text(test_stmt))
        engine.dispose()
        return True, "Connection successful!"
    except Exception as e:
        return False, str(e)

def inspect_schema(config: Dict[str, Any]) -> Dict[str, Any]:
    engine = get_engine(config)
    try:
        inspector = inspect(engine)
        tables_info = []
        views_info = []

        # Get tables
        for table in inspector.get_table_names():
            cols = []
            pk_cols = set(inspector.get_pk_constraint(table).get("constrained_columns", []))
            for col in inspector.get_columns(table):
                cols.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": col["name"] in pk_cols
                })
            tables_info.append({
                "name": table,
                "columns": cols,
                "primary_keys": list(pk_cols)
            })

        # Get views
        for view in inspector.get_view_names():
            cols = []
            for col in inspector.get_columns(view):
                cols.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                    "primary_key": False
                })
            views_info.append({
                "name": view,
                "columns": cols,
                "primary_keys": []
            })

        return {
            "tables": tables_info,
            "views": views_info
        }
    finally:
        engine.dispose()

def execute_raw_query(config: Dict[str, Any], query_sql: str, limit: int = 1000) -> Dict[str, Any]:
    engine = get_engine(config)
    start_time = time.time()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query_sql))
            exec_time_ms = round((time.time() - start_time) * 1000, 2)

            if result.returns_rows:
                columns = list(result.keys())
                raw_rows = result.fetchmany(limit)
                
                # Convert rows to dicts / JSON serializable types
                formatted_rows = []
                for row in raw_rows:
                    formatted_row = {}
                    for col, val in zip(columns, row):
                        if isinstance(val, (bytes, bytearray)):
                            formatted_row[col] = f"<binary {len(val)} bytes>"
                        else:
                            formatted_row[col] = str(val) if val is not None and not isinstance(val, (int, float, bool, str, list, dict)) else val
                    formatted_rows.append(formatted_row)

                return {
                    "status": "success",
                    "columns": columns,
                    "rows": formatted_rows,
                    "row_count": len(formatted_rows),
                    "execution_time_ms": exec_time_ms,
                    "returns_rows": True
                }
            else:
                conn.commit()
                return {
                    "status": "success",
                    "columns": [],
                    "rows": [],
                    "row_count": result.rowcount,
                    "execution_time_ms": exec_time_ms,
                    "returns_rows": False
                }
    except Exception as e:
        exec_time_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "status": "error",
            "error_message": str(e),
            "execution_time_ms": exec_time_ms
        }
    finally:
        engine.dispose()

def update_cell_value(
    config: Dict[str, Any],
    table_name: str,
    pk_col: str,
    pk_val: Any,
    col_name: str,
    new_val: Any
) -> Dict[str, Any]:
    engine = get_engine(config)
    start_time = time.time()
    try:
        with engine.connect() as conn:
            # Escape identifiers safely using text binding or dialect quotes
            sql = f"UPDATE {table_name} SET {col_name} = :new_val WHERE {pk_col} = :pk_val"
            res = conn.execute(text(sql), {"new_val": new_val, "pk_val": pk_val})
            conn.commit()
            exec_time = round((time.time() - start_time) * 1000, 2)
            return {
                "status": "success",
                "rows_affected": res.rowcount,
                "execution_time_ms": exec_time
            }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e)
        }
    finally:
        engine.dispose()
