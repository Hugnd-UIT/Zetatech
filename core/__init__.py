def create_app():
    from core.app import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
