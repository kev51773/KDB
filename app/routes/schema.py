from fastapi import APIRouter, HTTPException
import app.db_store as db_store
import app.db_engine as db_engine

router = APIRouter(prefix="/api/schema", tags=["schema"])

@router.get("/{conn_id}")
def get_schema(conn_id: int):
    conn_config = db_store.get_connection(conn_id)
    if not conn_config:
        raise HTTPException(status_code=404, detail="Connection configuration not found.")
    
    try:
        data = db_engine.inspect_schema(conn_config)
        data["is_read_only"] = bool(conn_config.get("is_read_only"))
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
