from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_token, decode_supabase_token
from app.core.exceptions import UnauthorizedError
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    # Try our own JWT first, fall back to Supabase JWT
    payload = None
    for decoder in [decode_token, decode_supabase_token]:
        try:
            payload = decoder(token)
            break
        except UnauthorizedError:
            continue

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.supabase_user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        # Create user on first auth (Supabase flow)
        email: str = payload.get("email", "")
        user = User(supabase_user_id=user_id, email=email)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
