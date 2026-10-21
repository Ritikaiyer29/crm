from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import create_access_token, get_current_user, verify_password
from api.schemas import LoginRequest, TokenResponse, UserOut
from database import get_session
from models import AppUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(AppUser).where(AppUser.email == body.email))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    token = create_access_token(user)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: AppUser = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
