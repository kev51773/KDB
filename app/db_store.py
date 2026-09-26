import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading

CONNECTIONS_PATH = Path("kdb_connections.json")
BOOKMARKS_PATH = Path("kdb_bookmarks.json")
HISTORY_PATH = Path("kdb_history.json")
STORE_PATH = Path("kdb_store.json")  # Legacy store file for automatic migration

_lock = threading.Lock()

def _read_connections() -> List[Dict[str, Any]]:
    if not CONNECTIONS_PATH.exists():
        return []
    try:
        with open(CONNECTIONS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _write_connections(data: List[Dict[str, Any]]):
    with open(CONNECTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _read_bookmarks_store() -> Dict[str, Any]:
    if not BOOKMARKS_PATH.exists():
        return {"bookmark_groups": [], "bookmarks": []}
    try:
        with open(BOOKMARKS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("bookmark_groups", [])
                data.setdefault("bookmarks", [])
                return data
            return {"bookmark_groups": [], "bookmarks": []}
    except Exception:
        return {"bookmark_groups": [], "bookmarks": []}

def _write_bookmarks_store(data: Dict[str, Any]):
    with open(BOOKMARKS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _read_history() -> List[Dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def _write_history(data: List[Dict[str, Any]]):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _get_next_id(items: List[Dict[str, Any]]) -> int:
    if not items:
        return 1
    return max((item.get("id") or 0) for item in items) + 1

def init_store_db():
    """Initialize local JSON store files if needed."""
    pass

# --- Connection CRUD ---

def list_connections() -> List[Dict[str, Any]]:
    with _lock:
        conns = _read_connections()
        return sorted(conns, key=lambda c: c.get("id", 0), reverse=True)

def get_connection(conn_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        conns = _read_connections()
        for c in conns:
            if c.get("id") == conn_id:
                return dict(c)
        return None

def save_connection(data: Dict[str, Any]) -> int:
    with _lock:
        conns = _read_connections()
        cid = data.get("id")
        is_ro = 1 if data.get("is_read_only") else 0

        if cid:
            for i, c in enumerate(conns):
                if c.get("id") == cid:
                    conns[i] = {
                        "id": cid,
                        "name": data["name"],
                        "db_type": data["db_type"],
                        "host": data.get("host"),
                        "port": data.get("port"),
                        "database": data["database"],
                        "username": data.get("username"),
                        "password": data.get("password") or c.get("password"),
                        "extra_params": data.get("extra_params"),
                        "is_read_only": is_ro,
                        "created_at": c.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
                    _write_connections(conns)
                    return cid

        new_id = _get_next_id(conns)
        new_conn = {
            "id": new_id,
            "name": data["name"],
            "db_type": data["db_type"],
            "host": data.get("host"),
            "port": data.get("port"),
            "database": data["database"],
            "username": data.get("username"),
            "password": data.get("password"),
            "extra_params": data.get("extra_params"),
            "is_read_only": is_ro,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        conns.append(new_conn)
        _write_connections(conns)
        return new_id

def delete_connection(conn_id: int):
    with _lock:
        conns = [c for c in _read_connections() if c.get("id") != conn_id]
        _write_connections(conns)

# --- Bookmark Groups CRUD ---

def list_bookmark_groups(connection_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])

        parent_map = {g["id"]: g.get("parent_id") for g in groups}
        conn_map = {g["id"]: g.get("connection_id") for g in groups}

        def get_effective_conn_id(gid):
            cid = conn_map.get(gid)
            if cid is not None:
                return cid
            pid = parent_map.get(gid)
            if pid:
                return get_effective_conn_id(pid)
            return None

        if connection_id:
            res_groups = []
            for g in groups:
                eff_cid = get_effective_conn_id(g["id"])
                if eff_cid == connection_id or eff_cid is None:
                    res_groups.append(g)
            groups = res_groups

        return sorted(groups, key=lambda g: (g.get("position", 0), g.get("id", 0)))

def save_bookmark_group(data: Dict[str, Any]) -> int:
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])
        gid = data.get("id")

        conn_id = data.get("connection_id")
        parent_id = data.get("parent_id") if "parent_id" in data else None
        if conn_id is None and parent_id:
            parent_group = next((g for g in groups if g.get("id") == parent_id), None)
            if parent_group:
                conn_id = parent_group.get("connection_id")

        if gid:
            for i, g in enumerate(groups):
                if g.get("id") == gid:
                    p_id = data["parent_id"] if "parent_id" in data else g.get("parent_id")
                    c_id = data["connection_id"] if "connection_id" in data else g.get("connection_id")
                    groups[i] = {
                        "id": gid,
                        "name": data.get("name") or g.get("name"),
                        "parent_id": p_id,
                        "connection_id": c_id,
                        "icon": data.get("icon") or g.get("icon", "folder"),
                        "color": data.get("color") or g.get("color", "#4F46E5"),
                        "position": data.get("position") if ("position" in data and data["position"] is not None) else g.get("position", 0),
                        "created_at": g.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
                    _write_bookmarks_store(bm_store)
                    return gid

        new_id = _get_next_id(groups)
        new_group = {
            "id": new_id,
            "name": data["name"],
            "parent_id": parent_id,
            "connection_id": conn_id,
            "icon": data.get("icon", "folder"),
            "color": data.get("color", "#4F46E5"),
            "position": data.get("position", 0),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        groups.append(new_group)
        _write_bookmarks_store(bm_store)
        return new_id

def delete_bookmark_group(group_id: int):
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])
        bookmarks = bm_store.get("bookmarks", [])

        def get_all_child_ids(gid: int) -> List[int]:
            cids = []
            for g in groups:
                if g.get("parent_id") == gid:
                    cid = g.get("id")
                    cids.append(cid)
                    cids.extend(get_all_child_ids(cid))
            return cids

        target_ids = set([group_id] + get_all_child_ids(group_id))

        bm_store["bookmark_groups"] = [g for g in groups if g.get("id") not in target_ids]
        bm_store["bookmarks"] = [b for b in bookmarks if b.get("group_id") not in target_ids]

        _write_bookmarks_store(bm_store)

# --- Bookmarks CRUD ---

def list_bookmarks(group_id: Optional[int] = None, connection_id: Optional[int] = None) -> List[Dict[str, Any]]:
    with _lock:
        bm_store = _read_bookmarks_store()
        bookmarks = bm_store.get("bookmarks", [])
        groups = bm_store.get("bookmark_groups", [])
        conns_map = {c["id"]: c["name"] for c in _read_connections()}
        groups_map = {g["id"]: g["name"] for g in groups}
        groups_conn_map = {g["id"]: g.get("connection_id") for g in groups}

        res = []
        for b in bookmarks:
            if group_id and b.get("group_id") != group_id:
                continue

            b_conn_id = b.get("connection_id")
            if b_conn_id is None and b.get("group_id"):
                b_conn_id = groups_conn_map.get(b.get("group_id"))

            if connection_id and b_conn_id and b_conn_id != connection_id:
                continue

            item = dict(b)
            if item.get("connection_id") is None and b_conn_id:
                item["connection_id"] = b_conn_id
            item["connection_name"] = conns_map.get(b_conn_id)
            item["group_name"] = groups_map.get(b.get("group_id"))
            res.append(item)

        return sorted(res, key=lambda b: (b.get("group_id") or 0, -b.get("id", 0)))

def save_bookmark(data: Dict[str, Any]) -> int:
    with _lock:
        bm_store = _read_bookmarks_store()
        bookmarks = bm_store.get("bookmarks", [])
        groups = bm_store.get("bookmark_groups", [])
        bm_id = data.get("id")

        conn_id = data.get("connection_id")
        if conn_id is None and data.get("group_id"):
            parent_group = next((g for g in groups if g.get("id") == data["group_id"]), None)
            if parent_group:
                conn_id = parent_group.get("connection_id")

        if bm_id:
            for i, b in enumerate(bookmarks):
                if b.get("id") == bm_id:
                    c_id = conn_id if conn_id is not None else b.get("connection_id")
                    bookmarks[i] = {
                        "id": bm_id,
                        "group_id": data.get("group_id"),
                        "title": data["title"],
                        "bookmark_type": data.get("bookmark_type", "query"),
                        "connection_id": c_id,
                        "sql_query": data.get("sql_query"),
                        "table_name": data.get("table_name"),
                        "notes": data.get("notes"),
                        "tags": data.get("tags"),
                        "created_at": b.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    }
                    _write_bookmarks_store(bm_store)
                    return bm_id

        new_id = _get_next_id(bookmarks)
        new_bm = {
            "id": new_id,
            "group_id": data.get("group_id"),
            "title": data["title"],
            "bookmark_type": data.get("bookmark_type", "query"),
            "connection_id": conn_id,
            "sql_query": data.get("sql_query"),
            "table_name": data.get("table_name"),
            "notes": data.get("notes"),
            "tags": data.get("tags"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        bookmarks.append(new_bm)
        _write_bookmarks_store(bm_store)
        return new_id

def delete_bookmark(bookmark_id: int):
    with _lock:
        bm_store = _read_bookmarks_store()
        bm_store["bookmarks"] = [b for b in bm_store.get("bookmarks", []) if b.get("id") != bookmark_id]
        _write_bookmarks_store(bm_store)

def _sanitize_export_item(item: Dict[str, Any]) -> Dict[str, Any]:
    clean = dict(item)
    clean.pop("connection_id", None)
    return clean

def export_bookmarks_data() -> Dict[str, Any]:
    with _lock:
        bm_store = _read_bookmarks_store()
        return {
            "version": 1,
            "groups": [_sanitize_export_item(g) for g in bm_store.get("bookmark_groups", [])],
            "bookmarks": [_sanitize_export_item(b) for b in bm_store.get("bookmarks", [])]
        }

def export_node_data(node_type: str, node_id: int) -> Dict[str, Any]:
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])
        bookmarks = bm_store.get("bookmarks", [])

        if node_type == "bookmark":
            bm = next((b for b in bookmarks if b.get("id") == node_id), None)
            if not bm:
                raise ValueError(f"Bookmark {node_id} not found")
            return {"version": 1, "groups": [], "bookmarks": [_sanitize_export_item(bm)]}
        
        elif node_type == "group":
            def get_all_child_ids(gid: int) -> List[int]:
                cids = []
                for g in groups:
                    if g.get("parent_id") == gid:
                        cid = g.get("id")
                        cids.append(cid)
                        cids.extend(get_all_child_ids(cid))
                return cids

            all_gids = set([node_id] + get_all_child_ids(node_id))
            export_groups = [_sanitize_export_item(g) for g in groups if g.get("id") in all_gids]
            export_bms = [_sanitize_export_item(b) for b in bookmarks if b.get("group_id") in all_gids]
            return {"version": 1, "groups": export_groups, "bookmarks": export_bms}

        else:
            raise ValueError(f"Invalid node_type: {node_type}")

def duplicate_bookmark(bookmark_id: int) -> int:
    with _lock:
        bm_store = _read_bookmarks_store()
        bookmarks = bm_store.get("bookmarks", [])
        original = next((b for b in bookmarks if b.get("id") == bookmark_id), None)
        if not original:
            raise ValueError(f"Bookmark {bookmark_id} not found")

        new_id = _get_next_id(bookmarks)
        new_bm = dict(original)
        new_bm["id"] = new_id
        new_bm["title"] = f"{original['title']} (Copy)"
        new_bm["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bookmarks.append(new_bm)
        _write_bookmarks_store(bm_store)
        return new_id

def duplicate_bookmark_group(group_id: int) -> int:
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])
        bookmarks = bm_store.get("bookmarks", [])
        
        target = next((g for g in groups if g.get("id") == group_id), None)
        if not target:
            raise ValueError(f"Bookmark group {group_id} not found")

        group_map = {}

        def clone_group_tree(original_gid: int, parent_override: Optional[int] = None) -> int:
            orig_g = next((g for g in groups if g.get("id") == original_gid), None)
            if not orig_g:
                return 0
            
            new_gid = _get_next_id(groups)
            name_text = f"{orig_g['name']} (Copy)" if original_gid == group_id else orig_g["name"]
            p_id = parent_override if parent_override is not None else orig_g.get("parent_id")
            
            new_g = dict(orig_g)
            new_g["id"] = new_gid
            new_g["name"] = name_text
            new_g["parent_id"] = p_id
            new_g["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            groups.append(new_g)
            group_map[original_gid] = new_gid

            child_gids = [g["id"] for g in list(groups) if g.get("parent_id") == original_gid and g.get("id") != new_gid]
            for c_gid in child_gids:
                clone_group_tree(c_gid, new_gid)

            return new_gid

        top_new_id = clone_group_tree(group_id, target.get("parent_id"))

        for orig_id, new_id in group_map.items():
            bms_in_group = [b for b in bookmarks if b.get("group_id") == orig_id]
            for bm in bms_in_group:
                new_bm_id = _get_next_id(bookmarks)
                new_bm = dict(bm)
                new_bm["id"] = new_bm_id
                new_bm["group_id"] = new_id
                new_bm["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                bookmarks.append(new_bm)

        _write_bookmarks_store(bm_store)
        return top_new_id

def import_bookmarks_data(data: Dict[str, Any], target_connection_id: Optional[int] = None):
    with _lock:
        bm_store = _read_bookmarks_store()
        groups = bm_store.get("bookmark_groups", [])
        bookmarks = bm_store.get("bookmarks", [])

        group_id_map = {}
        for g in data.get("groups", []):
            old_id = g.get("id")
            new_id = _get_next_id(groups)
            new_group = {
                "id": new_id,
                "name": g["name"],
                "parent_id": None,
                "connection_id": target_connection_id if target_connection_id is not None else g.get("connection_id"),
                "icon": g.get("icon", "folder"),
                "color": g.get("color", "#4F46E5"),
                "position": g.get("position", 0),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            groups.append(new_group)
            if old_id:
                group_id_map[old_id] = new_id

        # Preserve parent_id mapping for imported groups
        for g in data.get("groups", []):
            old_id = g.get("id")
            old_parent_id = g.get("parent_id")
            if old_id and old_parent_id and old_id in group_id_map and old_parent_id in group_id_map:
                imported_g = next((x for x in groups if x["id"] == group_id_map[old_id]), None)
                if imported_g:
                    imported_g["parent_id"] = group_id_map[old_parent_id]

        for bm in data.get("bookmarks", []):
            target_group_id = group_id_map.get(bm.get("group_id")) if bm.get("group_id") in group_id_map else bm.get("group_id")
            new_bm_id = _get_next_id(bookmarks)
            bookmarks.append({
                "id": new_bm_id,
                "group_id": target_group_id,
                "title": bm["title"],
                "bookmark_type": bm.get("bookmark_type", "query"),
                "connection_id": target_connection_id if target_connection_id is not None else bm.get("connection_id"),
                "sql_query": bm.get("sql_query"),
                "table_name": bm.get("table_name"),
                "notes": bm.get("notes"),
                "tags": bm.get("tags"),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        _write_bookmarks_store(bm_store)

# --- History ---

MAX_HISTORY_ENTRIES = 500

def add_query_history(conn_id: Optional[int], sql: str, exec_time: float, row_count: int, status: str, err: Optional[str] = None):
    with _lock:
        history = _read_history()
        new_id = _get_next_id(history)
        history.append({
            "id": new_id,
            "connection_id": conn_id,
            "sql_query": sql,
            "execution_time_ms": exec_time,
            "row_count": row_count,
            "status": status,
            "error_message": err,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        if len(history) > MAX_HISTORY_ENTRIES:
            history = history[-MAX_HISTORY_ENTRIES:]
        _write_history(history)

def list_query_history(limit: int = 50) -> List[Dict[str, Any]]:
    with _lock:
        history = _read_history()
        conns_map = {c["id"]: c["name"] for c in _read_connections()}

        sorted_hist = sorted(history, key=lambda h: h.get("id", 0), reverse=True)[:limit]
        res = []
        for h in sorted_hist:
            item = dict(h)
            item["connection_name"] = conns_map.get(h.get("connection_id"))
            res.append(item)
        return res
