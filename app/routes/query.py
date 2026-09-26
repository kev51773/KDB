from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import app.db_store as db_store
import app.db_engine as db_engine

router = APIRouter(prefix="/api/query", tags=["query"])

class QueryRequest(BaseModel):
    connection_id: int
    sql_query: str
    limit: Optional[int] = 1000

@router.post("/execute")
def execute_query(req: QueryRequest):
    conn_config = db_store.get_connection(req.connection_id)
    if not conn_config:
        raise HTTPException(status_code=404, detail="Connection profile not found.")
    
    # Block write operations if Read-Only mode active
    if conn_config.get("is_read_only"):
        import sqlglot
        from sqlglot import exp
        is_write = False
        try:
            parsed = sqlglot.parse_one(req.sql_query)
            if parsed and parsed.find(exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.AlterTable):
                is_write = True
        except Exception:
            import re
            if re.search(r'\b(insert|update|delete|drop|alter|truncate)\b', req.sql_query, re.IGNORECASE):
                is_write = True
        
        if is_write:
            raise HTTPException(status_code=403, detail="Execution blocked: Active connection is configured in Read-Only mode.")

    res = db_engine.execute_raw_query(conn_config, req.sql_query, limit=req.limit or 1000)
    
    # Record history
    db_store.add_query_history(
        conn_id=req.connection_id,
        sql=req.sql_query,
        exec_time=res.get("execution_time_ms", 0),
        row_count=res.get("row_count", 0),
        status=res.get("status", "error"),
        err=res.get("error_message")
    )

    return res

class AutocompleteRequest(BaseModel):
    connection_id: int
    sql_query: str
    cursor_pos: int

@router.post("/autocomplete")
def autocomplete_endpoint(req: AutocompleteRequest):
    conn_config = db_store.get_connection(req.connection_id)
    if not conn_config:
        return {"suggestions": []}
    
    try:
        schema_data = db_engine.inspect_schema(conn_config)
    except Exception:
        schema_data = {"tables": [], "views": []}

    schema_data["is_read_only"] = bool(conn_config.get("is_read_only"))

    import app.sql_completer as sql_completer
    suggestions = sql_completer.get_sql_completions(
        sql_query=req.sql_query,
        cursor_pos=req.cursor_pos,
        schema_data=schema_data
    )
    return {"suggestions": suggestions}

@router.get("/history")
def get_history(limit: int = 50):
    return db_store.list_query_history(limit=limit)
