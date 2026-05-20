from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWTError
from config import AI_JWT_PUBLIC_KEY, AI_JWT_ISS, AI_JWT_AUD, ADMIN_JWT_SECRET

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
                options={"verify_sub": False}
            )
    except PyJWTError as e:
        print(f"JWT Verification Error: {e}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return {
        "user_id": str(user_id),
        "username": payload.get("username"),
        "full_name": payload.get("full_name") or payload.get("name"),
        "email": payload.get("email"),
        "profile_pic": payload.get("profile_image") or payload.get("profile_pic") or payload.get("avatar_url") or payload.get("photo"),
        "user_type": payload.get("user_type"),
    }

def verify_admin_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            ADMIN_JWT_SECRET,
            algorithms=["HS256"]
        )
    except PyJWTError as e:
        print(f"Admin JWT Verification Error: {e}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired admin token: {e}",
        )

    if payload.get("user_type") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return payload
