from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from ..auth import verify_jwt
import config
from .service import build_payment_transaction, verify_payment

router = APIRouter(prefix="/stellar", tags=["Stellar Payments"])

class InitPaymentRequest(BaseModel):
    public_key: str
    amount: str
    memo: str = None

class VerifyPaymentRequest(BaseModel):
    tx_hash: str

@router.post("/payment/initialize")
async def initialize_payment(payload: InitPaymentRequest, user=Depends(verify_jwt)):
    if not config.STELLAR_PAYMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Stellar payments feature is disabled")
        
    try:
        xdr = await build_payment_transaction(payload.public_key, payload.amount, payload.memo)
        return {"xdr": xdr}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build transaction: {str(e)}")

@router.post("/payment/verify")
async def check_payment(payload: VerifyPaymentRequest, user=Depends(verify_jwt)):
    if not config.STELLAR_PAYMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Stellar payments feature is disabled")
        
    is_valid = await verify_payment(payload.tx_hash)
    
    if is_valid:
        # Here we would normally record the purchase in the database
        # For now, just return success
        return {"status": "success", "message": "Payment verified successfully"}
    else:
        raise HTTPException(status_code=400, detail="Payment verification failed or transaction not found")

@router.get("/wallet/info")
async def wallet_info():
    if not config.STELLAR_PAYMENTS_ENABLED:
        raise HTTPException(status_code=404, detail="Stellar payments feature is disabled")
        
    return {
        "public_key": config.STELLAR_PLATFORM_PUBLIC_KEY,
        "network": config.STELLAR_NETWORK
    }
