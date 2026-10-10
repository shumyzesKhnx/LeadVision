"""Beginner-friendly start command: python -m app."""

import logging
import sys

import uvicorn
from pydantic import ValidationError

from app.modules.foundation.config import Settings


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        print("Invalid configuration. Check .env against .env.example.", file=sys.stderr)
        raise SystemExit(1) from None
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    from app.main import create_app

    uvicorn.run(
        create_app(settings), host=settings.api_host, port=settings.api_port,
        log_level=settings.log_level.lower(), access_log=False,
    )


if __name__ == "__main__":
    main()
