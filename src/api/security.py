import time
from flask import request, jsonify, abort
from functools import wraps
from src.config import config
import re

# In-memory rate limiting dictionary: { ip_address: [timestamp1, timestamp2, ...] }
_rate_limits = {}

def sanitize_slug(topic: str) -> str:
    """
    Strictly sanitizes user input to prevent Path Traversal (LFI) and bad queries.
    Only allows alphanumeric characters and underscores.
    """
    if not topic:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")
    return slug[:60]

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow passing via Header or Query Param for flexibility
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key or key != config.APP_API_KEY:
            return jsonify({"error": "Unauthorized. Invalid or missing API Key."}), 401
        return f(*args, **kwargs)
    return decorated_function

def rate_limit(max_requests: int = 10, window_seconds: int = 60):
    """
    A lightweight, in-memory IP rate limiter to prevent abuse and API credit exhaustion.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr
            now = time.time()
            
            if ip not in _rate_limits:
                _rate_limits[ip] = []
                
            # Remove timestamps older than the window
            _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < window_seconds]
            
            if len(_rate_limits[ip]) >= max_requests:
                return jsonify({
                    "error": "Too Many Requests. You have been rate limited."
                }), 429
                
            _rate_limits[ip].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
