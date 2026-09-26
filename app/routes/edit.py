from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import app.db_store as db_store
import app.db_engine as db_engine

router = APIRouter(prefix="/api/edit", tags=["edit"])

class CellUpdateRequest(BaseModel):
    connection_id: int
    table_name: str
    pk_column: str
    pk_value: Any
    column_name: str
    new_value: Any

@router.post("/cell")
def update_cell(req: CellUpdateRequest):
    conn_config = db_store.get_connection(req.connection_id)
    if not conn_config:
        raise HTTPException(status_code=404, detail="Connection profile not found.")
    
    if conn_config.get("is_read_only"):
        raise HTTPException(status_code=403, detail="Cell editing blocked: Connection is configured in Read-Only mode.")
    
    res = db_engine.update_cell_value(
        config=conn_config,
        table_name=req.table_name,
        pk_col=req.pk_column,
        pk_val=req.pk_value,
        col_name=req.column_name,
        new_val=req.new_value
    )
    
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("error_message", "Failed to update cell."))
    
    return res
