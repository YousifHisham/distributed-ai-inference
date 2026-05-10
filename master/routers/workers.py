import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from common.models import WorkerRegistration, Heartbeat
from master.main import app_state

router = APIRouter(tags=["workers"])


class DeregisterRequest(BaseModel):
    node_id: str


@router.post("/workers/register")
async def register_worker(reg: WorkerRegistration):
    registry = app_state.get("registry")
    if not registry:
        raise HTTPException(status_code=503, detail="Service not ready")
    existing = registry.get(reg.node_id)
    worker = await registry.register(reg)
    status = "updated" if existing else "registered"
    return {"status": status, "node_id": worker.node_id}


@router.post("/workers/heartbeat")
async def worker_heartbeat(hb: Heartbeat):
    registry = app_state.get("registry")
    if not registry:
        raise HTTPException(status_code=503, detail="Service not ready")
    worker = await registry.update_heartbeat(hb)
    if worker is None:
        return {"status": "re_register", "server_time": time.time()}
    return {"status": "ok", "server_time": time.time()}


@router.post("/workers/deregister")
async def deregister_worker(body: DeregisterRequest):
    registry = app_state.get("registry")
    if not registry:
        raise HTTPException(status_code=503, detail="Service not ready")
    await registry.deregister(body.node_id)
    return {"status": "draining", "node_id": body.node_id}
