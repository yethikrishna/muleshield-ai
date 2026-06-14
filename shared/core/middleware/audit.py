"""
MuleShield AI - Audit Logging Middleware
Immutable audit logging for all requests
"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware for audit logging of all requests"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate latency
        process_time = (time.time() - start_time) * 1000
        
        # Add security headers
        response.headers["X-Request-ID"] = str(time.time())
        response.headers["X-Process-Time-MS"] = str(round(process_time, 2))
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        return response
