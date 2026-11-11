from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from react_agent.backend.auth.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from react_agent.backend.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from react_agent.backend.db.database import get_db
from react_agent.backend.db.models import User

router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


# ===================== AUTH =====================
@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    existing_user = db.query(User).filter(User.email == request.email).first()

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)

    return AuthResponse(
        access_token=token,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == request.email).first()

    if user is None or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)

    return AuthResponse(
        access_token=token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def me(
    user: User = Depends(get_current_user),
):
    return UserResponse(
        id=user.id,
        email=user.email,
    )
