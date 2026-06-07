import os
from flask import Flask
from datetime import datetime

from app.routes import register_routes
from app.openapi import register_openapi


# Support both older Flask (json encoder) and newer Flask (json provider)
JSON_PROVIDER_CLASS = None
JSON_ENCODER_CLASS = None
try:
    from flask.json.provider import DefaultJSONProvider as BaseJSONProvider

    class CustomJSONProvider(BaseJSONProvider):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.replace(microsecond=0).isoformat() + "Z"
            return super().default(obj)

    JSON_PROVIDER_CLASS = CustomJSONProvider
except Exception:
    try:
        from flask.json import JSONEncoder as BaseJSONEncoder

        class CustomJSONEncoder(BaseJSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.replace(microsecond=0).isoformat() + "Z"
                return super().default(obj)

        JSON_ENCODER_CLASS = CustomJSONEncoder
    except Exception:
        JSON_PROVIDER_CLASS = None
        JSON_ENCODER_CLASS = None


def create_app():
    templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    app = Flask(__name__, template_folder=templates_dir)
    if JSON_PROVIDER_CLASS is not None:
        try:
            app.json_provider_class = JSON_PROVIDER_CLASS
            app.json = app.json_provider_class(app)
        except Exception:
            # fallback: try setting encoder if available
            if JSON_ENCODER_CLASS is not None:
                app.json_encoder = JSON_ENCODER_CLASS
    else:
        if JSON_ENCODER_CLASS is not None:
            app.json_encoder = JSON_ENCODER_CLASS

    register_routes(app)
    register_openapi(app)
    return app
