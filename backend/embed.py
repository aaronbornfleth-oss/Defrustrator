"""Shopify / Left Coast iframe and CORS allowlists.

The UI is meant to load inside a Shopify page iframe (?embed=1). Browsers
honor CSP frame-ancestors (not CORS) for that. Do not set X-Frame-Options
to DENY or SAMEORIGIN — that would block the storefront embed.
"""
from starlette.middleware.base import BaseHTTPMiddleware

FRAME_ANCESTORS = (
    "'self' "
    "https://*.myshopify.com https://admin.shopify.com https://*.shopify.com "
    "https://leftcoastoriginal.com https://www.leftcoastoriginal.com https://*.leftcoastoriginal.com "
    "https://leftcoastcabinets.com https://www.leftcoastcabinets.com https://*.leftcoastcabinets.com"
)

CSP = f"frame-ancestors {FRAME_ANCESTORS}"

CORS_ORIGINS = [
    'https://leftcoastoriginal.com',
    'https://www.leftcoastoriginal.com',
    'https://leftcoastcabinets.com',
    'https://www.leftcoastcabinets.com',
    'https://admin.shopify.com',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# Storefronts (*.myshopify.com), Shopify admin, and Left Coast custom domains.
CORS_ORIGIN_REGEX = (
    r'https://([a-z0-9-]+\.)*(myshopify\.com|shopify\.com|'
    r'leftcoastoriginal\.com|leftcoastcabinets\.com)'
)


class EmbedHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if 'x-frame-options' in response.headers:
            del response.headers['x-frame-options']
        response.headers['Content-Security-Policy'] = CSP
        response.headers['Permissions-Policy'] = (
            'clipboard-write=(self), clipboard-read=(self)'
        )
        return response
