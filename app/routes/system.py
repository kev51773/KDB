import os
import signal
import threading
import time
from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["system"])

def _shutdown_process():
    time.sleep(0.5)
    os.kill(os.getpid(), signal.SIGINT)

@router.post("/shutdown")
def shutdown_server():
    threading.Thread(target=_shutdown_process, daemon=True).start()
    return {"status": "success", "message": "Server shutting down..."}
