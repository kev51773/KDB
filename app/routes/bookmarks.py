from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import app.db_store as db_store

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])

class BookmarkGroupModel(BaseModel):
    id: Optional[int] = None
    name: str
    parent_id: Optional[int] = None
    connection_id: Optional[int] = None
    icon: Optional[str] = "folder"
    color: Optional[str] = "#4F46E5"
    position: Optional[int] = 0

class BookmarkModel(BaseModel):
    id: Optional[int] = None
    group_id: Optional[int] = None
    title: str
    bookmark_type: Optional[str] = "query"
    connection_id: Optional[int] = None
    sql_query: Optional[str] = None
    table_name: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None

# --- Groups ---

@router.get("/groups", response_model=List[Dict[str, Any]])
def list_groups(connection_id: Optional[int] = None):
    return db_store.list_bookmark_groups(connection_id=connection_id)

@router.post("/groups")
def save_group(group: BookmarkGroupModel):
    group_id = db_store.save_bookmark_group(group.model_dump())
    return {"status": "success", "id": group_id}

@router.delete("/groups/{group_id}")
def delete_group(group_id: int):
    db_store.delete_bookmark_group(group_id)
    return {"status": "success"}

@router.post("/groups/{group_id}/duplicate")
def duplicate_group(group_id: int):
    new_id = db_store.duplicate_bookmark_group(group_id)
    return {"status": "success", "id": new_id}

@router.get("/groups/{group_id}/export")
def export_group(group_id: int):
    return db_store.export_node_data("group", group_id)

# --- Bookmarks ---

@router.get("", response_model=List[Dict[str, Any]])
def get_bookmarks(group_id: Optional[int] = None, connection_id: Optional[int] = None):
    return db_store.list_bookmarks(group_id=group_id, connection_id=connection_id)

@router.post("")
def save_bookmark(bm: BookmarkModel):
    bm_id = db_store.save_bookmark(bm.model_dump())
    return {"status": "success", "id": bm_id}

@router.delete("/{bm_id}")
def delete_bookmark(bm_id: int):
    db_store.delete_bookmark(bm_id)
    return {"status": "success"}

@router.post("/{bm_id}/duplicate")
def duplicate_bookmark(bm_id: int):
    new_id = db_store.duplicate_bookmark(bm_id)
    return {"status": "success", "id": new_id}

@router.get("/{bm_id}/export")
def export_bookmark(bm_id: int):
    return db_store.export_node_data("bookmark", bm_id)

@router.get("/export")
def export_bookmarks():
    return db_store.export_bookmarks_data()

@router.post("/import")
def import_bookmarks(data: Dict[str, Any], connection_id: Optional[int] = None):
    target_conn_id = connection_id if connection_id is not None else data.get("connection_id")
    db_store.import_bookmarks_data(data, target_connection_id=target_conn_id)
    return {"status": "success"}
