from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWTError
from config import AI_JWT_PUBLIC_KEY, AI_JWT_ISS, AI_JWT_AUD

security = HTTPBearer()

def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
            payload = jwt.decode(
                token,
                AI_JWT_PUBLIC_KEY,
                algorithms=["RS256"],
                audience=AI_JWT_AUD, 
                issuer=AI_JWT_ISS,
            )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "user_type": payload.get("user_type"),
    }
