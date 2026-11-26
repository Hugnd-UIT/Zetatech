import os
from dataclasses import dataclass

__version__ = "0.2.0"
__author__ = "Hugnd-UIT (Zetatech)"

RUNTIME_VERSION_ENV = "ZETATECH_IMAGE_VERSION"
RUNTIME_TAG_ENV = "ZETATECH_IMAGE_TAG"
RUNTIME_BUILD_ENV = "ZETATECH_IMAGE_BUILD"
UNKNOWN_VERSION = "unknown"


@dataclass(frozen=True)
class RuntimeMetadata:
    current_version: str
    current_tag: str
    build_id: str | None
    status: str


def _norm(val: str | None) -> str:
    return (val or "").strip()


def get_runtime_metadata() -> RuntimeMetadata:
    version = _norm(os.getenv(RUNTIME_VERSION_ENV))
    tag = _norm(os.getenv(RUNTIME_TAG_ENV))
    build_id = _norm(os.getenv(RUNTIME_BUILD_ENV)) or None

    if version and tag:
        return RuntimeMetadata(
            current_version=version,
            current_tag=tag,
            build_id=build_id,
            status="ready",
        )

    if not version and not tag:
        return RuntimeMetadata(
            current_version=__version__,
            current_tag=__version__,
            build_id=build_id,
            status="fallback",
        )

    return RuntimeMetadata(
        current_version=UNKNOWN_VERSION,
        current_tag=UNKNOWN_VERSION,
        build_id=build_id,
        status="degraded",
    )
