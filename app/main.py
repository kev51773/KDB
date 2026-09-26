from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

import app.db_store as db_store
from app.routes import connections, schema, query, edit, bookmarks

app = FastAPI(title="KDB - Personal QA Database Tool", version="1.0.0")

# Initialize store DB on startup
@app.on_event("startup")
def startup_event():
    db_store.init_store_db()

# Include routers
app.include_router(connections.router)
app.include_router(schema.router)
app.include_router(query.router)
app.include_router(edit.router)
app.include_router(bookmarks.router)

# Static files & frontend
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    return FileResponse(static_dir / "index.html")
