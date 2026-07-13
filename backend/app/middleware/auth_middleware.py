from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse
from app.core.internal_auth import verify_internal_context

from app.core.auth_service import verify_supabase_jwt, JWTError

PUBLIC_PATHS = [
    "/",  # your "health" endpoint
    "/docs",
    "/openapi.json",
    "/api/v1/openapi.json",
    "/redoc",
    "/health",
    "/auth/",
    "/auth/callback",
    "/stripe/webhook",
]

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Allow CORS preflight requests to pass through without auth
        if request.method == "OPTIONS":
            return await call_next(request)

        # Mastra is a private service. It may call only the explicitly scoped
        # Atlas tool boundary with a short-lived signed context. No public
        # bearer token is accepted as a substitute for this boundary.
        if path.startswith("/internal/atlas/"):
            context = request.headers.get("X-Atlas-Internal-Context", "")
            signature = request.headers.get("X-Atlas-Internal-Signature", "")
            try:
                claims = verify_internal_context(context, signature)
                request.state.internal_context = claims
                request.state.user = {"sub": claims["userId"]}
            except Exception:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid internal service context"},
                )
            return await call_next(request)

        # Allow all public paths
        for p in PUBLIC_PATHS:
            if path == p or (p != "/" and path.startswith(p)):
                return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing Bearer token"},
            )

        token = auth_header.split(" ", 1)[1]

        try:
            claims = await verify_supabase_jwt(token)
            request.state.user = claims
        except JWTError as e:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": str(e)},
            )
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)
