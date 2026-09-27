from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import app.db_store as db_store
import app.db_engine as db_engine

router = APIRouter(prefix="/api/connections", tags=["connections"])

class ConnectionModel(BaseModel):
    id: Optional[int] = None
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: str
    username: Optional[str] = None
    password: Optional[str] = None
    extra_params: Optional[str] = None
    is_read_only: Optional[bool] = False

@router.get("", response_model=List[Dict[str, Any]])
def get_connections():
    return db_store.list_connections()

@router.post("")
def save_connection(conn: ConnectionModel):
    conn_id = db_store.save_connection(conn.model_dump())
    return {"status": "success", "id": conn_id}

@router.delete("/{conn_id}")
def delete_connection(conn_id: int):
    db_store.delete_connection(conn_id)
    return {"status": "success"}

@router.post("/test")
def test_connection_endpoint(conn: ConnectionModel):
    payload = conn.model_dump()
    if conn.id and not payload.get("password"):
        existing = db_store.get_connection(conn.id)
        if existing and existing.get("password"):
            payload["password"] = existing.get("password")
            
    ok, msg = db_engine.test_connection(payload)
    if not ok:
        return {"status": "error", "message": msg}
    return {"status": "success", "message": msg}
