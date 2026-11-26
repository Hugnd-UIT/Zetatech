#!/usr/bin/env python3
"""Zetatech web launcher."""

import os
import uvicorn

from core.app import create_app


def main() -> None:
    app = create_app()
    host = os.getenv("ZETATECH_HOST", "127.0.0.1")
    port = int(os.getenv("ZETATECH_PORT", "8080"))
    uvicorn.run(app, host=host, port=port, log_level="warning", workers=1)


if __name__ == "__main__":
    main()
