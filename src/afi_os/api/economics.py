from fastapi import APIRouter, HTTPException

from afi_os.schemas import EconomicsEvaluateRequest, EconomicsEvaluateResponse
from afi_os.services.economics import EconomicsInput, evaluate_economics

router = APIRouter(prefix="/api/economics", tags=["economics"])


@router.post("/evaluate", response_model=EconomicsEvaluateResponse)
def evaluate(payload: EconomicsEvaluateRequest) -> EconomicsEvaluateResponse:
    try:
        result = evaluate_economics(EconomicsInput(**payload.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EconomicsEvaluateResponse(**result.__dict__)
