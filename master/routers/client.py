import uuid
import logging

from fastapi import APIRouter, HTTPException, Request

from common.models import ClientInferRequest, InferenceResponse
from master.scheduler import NoHealthyWorkersError, AllRetriesExhaustedError

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/infer", response_model=InferenceResponse)
async def infer(body: ClientInferRequest, request: Request) -> InferenceResponse:
    scheduler = request.app.state.scheduler
    request_id = str(uuid.uuid4())

    try:
        return await scheduler.dispatch(body.query, request_id)
    except NoHealthyWorkersError:
        raise HTTPException(status_code=503, detail="No healthy workers available")
    except AllRetriesExhaustedError:
        raise HTTPException(status_code=504, detail="All worker retries exhausted")
