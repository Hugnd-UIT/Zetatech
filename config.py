"""
Zetatech Configuration and Constants

All global constants, tag sets, and color definitions.
"""

from typing import Final, Set


CURRENT_WP_VERSION: Final[float] = 6.7


MAX_POOL_SIZE: Final[int] = 50


DEFAULT_QUERY_LIMIT: Final[int] = 100
MAX_QUERY_LIMIT: Final[int] = 1000
MAX_CATALOG_SESSION_LIMIT: Final[int] = 500


RISKY_TAGS: Set[str] = {

    "ecommerce",
    "woocommerce",
    "payment",
    "gateway",
    "stripe",
    "paypal",
    "checkout",
    "cart",
    "shop",

    "form",
    "contact",
    "input",
    "survey",
    "quiz",
    "poll",
    "booking",
    "reservation",

    "upload",
    "file",
    "image",
    "gallery",
    "media",
    "download",
    "import",
    "export",
    "backup",

    "login",
    "register",
    "membership",
    "user",
    "profile",
    "admin",
    "role",
    "authentication",

    "chat",
    "ticket",
    "support",
    "comment",
    "review",
    "rating",
    "forum",
    "message",

    "api",
    "rest",
    "endpoint",
    "ajax",
    "query",
    "database",
    "sql",
    "db",
    "webhook",

    "calendar",
    "event",
    "booking",
    "appointment",
    "schedule",

    "oauth",
    "token",
    "sso",
    "ldap",
    "2fa",
    "captcha",

    "custom-post-type",
    "cpt",
    "meta",
    "field",
    "acf",
}

USER_FACING_TAGS: Set[str] = {
    "chat",
    "contact",
    "form",
    "gallery",
    "slider",
    "calendar",
    "booking",
    "appointment",
    "event",
    "social",
    "share",
    "comment",
    "review",
    "forum",
    "membership",
    "profile",
    "login",
    "register",
    "ecommerce",
    "shop",
    "cart",
    "product",
    "checkout",
    "newsletter",
    "popup",
    "banner",
    "map",
    "faq",
    "survey",
    "poll",
    "quiz",
    "ticket",
    "support",
    "download",
    "frontend",
    "video",
    "audio",
    "player",
    "gamification",
    "badge",
    "points",
}

SECURITY_KEYWORDS: Set[str] = {
    "xss",
    "sql",
    "injection",
    "security",
    "vulnerability",
    "exploit",
    "csrf",
    "rce",
    "ssrf",
    "lfi",
    "rfi",
    "idor",
    "xxe",
    "deserialization",
    "bypass",
    "privilege escalation",
    "fix",
    "patched",
    "sanitize",
    "escape",
    "harden",
    "cve-",
    "authentication bypass",
    "authorization",
    "nonce",
    "validation",
    "security update",
    "security fix",
}

FEATURE_KEYWORDS: Set[str] = {
    "added",
    "new",
    "feature",
    "support for",
    "introduced",
    "now allows",
    "implementation",
    "custom endpoint",
    "custom ajax",
    "custom api",
    "file upload",
    "import tool",
    "export",
    "rest api",
    "guest access",
    "public access",
    "allows users",
    "direct access",
    "shortcode",
    "widget",
    "custom post type",
}
