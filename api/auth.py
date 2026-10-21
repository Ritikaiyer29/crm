"""
JWT-based auth for the FastAPI app. Self-managed (bcrypt password hashes in
app_users.hashed_password, our own JWTs) rather than Supabase's separate
Auth product -- the schema was already designed this way back in Phase 1
(app_users.hashed_password existed before any of Phase 8 was built), so
this isn't a new architecture decision, just implementing one already made.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

load_dotenv()
from database import get_session
from models import AppUser

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h -- long enough a demo walkthrough won't expire mid-session

# bcrypt directly, not passlib's CryptContext: passlib 1.7.4's bcrypt backend
# self-test is broken against bcrypt>=4.1 (removed the __about__ attribute
# passlib's version probe relies on, surfacing as a bogus "password cannot
# be longer than 72 bytes" error on the very first hash call). passlib
# hasn't been updated for this; calling bcrypt directly sidesteps it.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")  # tokenUrl lets /docs "Authorize" work out of the box


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user: AppUser) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "org_id": str(user.org_id),
        "role": user.role.value,
        "exp": expire,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> AppUser:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = session.get(AppUser, user_id)
    if user is None:
        raise credentials_error
    return user
