"""
MuleShield AI - JWT Authentication + RBAC
Full RBAC implementation with 4 roles and permission matrix
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from enum import Enum

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "muleshield-boi-cybershield-2026-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

security = HTTPBearer()


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    AUDITOR = "AUDITOR"
    READONLY = "READONLY"


# Role Permissions Matrix
PERMISSIONS = {
    UserRole.ADMIN: {
        "transactions": ["read", "write", "delete"],
        "cases": ["read", "write", "delete", "assign"],
        "alerts": ["read", "write", "delete"],
        "users": ["read", "write", "delete"],
        "reports": ["read", "write", "generate"],
        "settings": ["read", "write"],
    },
    UserRole.INVESTIGATOR: {
        "transactions": ["read"],
        "cases": ["read", "write", "assign"],
        "alerts": ["read", "write"],
        "users": ["read"],
        "reports": ["read", "generate"],
        "settings": ["read"],
    },
    UserRole.AUDITOR: {
        "transactions": ["read"],
        "cases": ["read"],
        "alerts": ["read"],
        "users": ["read"],
        "reports": ["read", "write", "generate"],
        "settings": ["read"],
    },
    UserRole.READONLY: {
        "transactions": ["read"],
        "cases": ["read"],
        "alerts": ["read"],
        "users": [],
        "reports": ["read"],
        "settings": [],
    },
}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def has_permission(role: UserRole, resource: str, action: str) -> bool:
    """Check if role has permission for resource/action"""
    role_perms = PERMISSIONS.get(role, {})
    resource_perms = role_perms.get(resource, [])
    return action in resource_perms


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """FastAPI dependency for authenticated user"""
    token = credentials.credentials
    payload = decode_token(token)
    username: str = payload.get("sub")
    role: str = payload.get("role", UserRole.READONLY)
    
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    return {"username": username, "role": role}


class RBACDependency:
    """Class-based dependency for RBAC endpoint protection"""
    def __init__(self, resource: str, action: str):
        self.resource = resource
        self.action = action
    
    async def __call__(self, user: Dict = Depends(get_current_user)) -> Dict:
        role = UserRole(user["role"])
        if not has_permission(role, self.resource, self.action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: {self.resource}:{self.action}",
            )
        return user


def require_permission(resource: str, action: str):
    """Factory function for RBAC dependency"""
    return RBACDependency(resource, action)


# Predefined dependencies
require_admin = RBACDependency("settings", "write")
require_investigator = RBACDependency("cases", "write")
require_auditor = RBACDependency("reports", "generate")
require_read = RBACDependency("transactions", "read")
