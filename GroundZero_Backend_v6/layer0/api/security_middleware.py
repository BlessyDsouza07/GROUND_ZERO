"""
Phase 2 Implementation: Security middleware and request validation.

Adds:
1. Security headers (HSTS, CSP, X-Content-Type-Options, etc.)
2. Request validation (size limits, content type checking)
3. Response security headers
4. Request ID tracking
5. Comprehensive logging
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("groundzero.security")

# Request/response size limits
MAX_REQUEST_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_BODY_SIZE_BYTES = 1 * 1024 * 1024  # 1MB for JSON payloads


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers (OWASP recommendations)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate and log requests."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID for tracking
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE_BYTES:
            logger.warning(
                "Request too large [%s]: %s %s (%s bytes)",
                request_id,
                request.method,
                request.url.path,
                content_length,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "error": "Payload too large",
                    "detail": f"Request body exceeds {MAX_BODY_SIZE_BYTES} bytes",
                    "request_id": request_id,
                },
            )
        
        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "").lower()
            if content_type and "application/json" not in content_type:
                logger.warning(
                    "Invalid content type [%s]: %s %s (content-type: %s)",
                    request_id,
                    request.method,
                    request.url.path,
                    content_type,
                )
                return JSONResponse(
                    status_code=415,
                    content={
                        "error": "Unsupported media type",
                        "detail": "Only application/json is accepted",
                        "request_id": request_id,
                    },
                )
        
        # Log request
        logger.debug(
            "Request [%s]: %s %s (remote: %s)",
            request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        
        # Process request
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            logger.error(
                "Unhandled error [%s]: %s %s — %s",
                request_id,
                request.method,
                request.url.path,
                exc,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": "An unexpected error occurred",
                    "request_id": request_id,
                },
            )


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Sanitize inputs to prevent injection attacks."""
    
    DANGEROUS_PATTERNS = [
        "<script",
        "javascript:",
        "onclick",
        "onload",
        "onerror",
    ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get raw body if it exists
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                body_str = body.decode("utf-8", errors="ignore").lower()
                
                # Check for dangerous patterns
                for pattern in self.DANGEROUS_PATTERNS:
                    if pattern in body_str:
                        request_id = getattr(request.state, "request_id", "unknown")
                        logger.warning(
                            "Potential XSS/injection attempt [%s]: %s %s (pattern: %s)",
                            request_id,
                            request.method,
                            request.url.path,
                            pattern,
                        )
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": "Invalid input",
                                "detail": "Request contains potentially dangerous content",
                                "request_id": request_id,
                            },
                        )
            except Exception as exc:
                logger.debug("Input sanitization check failed: %s", exc)
                # Don't fail on sanitization errors, just log and continue
        
        return await call_next(request)


def add_security_middleware(app) -> None:
    """Register all security middleware on the FastAPI app."""
    # Order matters: register in reverse order of execution
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(RequestValidationMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security middleware registered")
