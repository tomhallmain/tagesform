"""
conftest for tests/unit/.

Mirrors the module-level env var bootstrap from the root conftest.py. This is
necessary because pytest loads each directory's conftest before collecting
tests in that directory, and the singletons may not yet be isolated when the
root conftest runs in some collection orders (e.g. `pytest tests/unit/`
invoked directly). Guarded on TAGESFORM_CACHE_DIR so the root conftest's
values win if it already ran; this just ensures they're present either way.
"""

import os

if "TAGESFORM_CACHE_DIR" not in os.environ:
    import atexit
    import shutil
    import tempfile

    _tmp = tempfile.mkdtemp(prefix="tagesform_unit_")
    os.environ["TAGESFORM_CACHE_DIR"] = os.path.join(_tmp, "cache")
    os.environ["TAGESFORM_CONFIG_DIR"] = os.path.join(_tmp, "config")
    os.environ["TAGESFORM_DATA_DIR"] = os.path.join(_tmp, "data")
    os.makedirs(os.environ["TAGESFORM_CACHE_DIR"], exist_ok=True)
    os.makedirs(os.environ["TAGESFORM_CONFIG_DIR"], exist_ok=True)
    os.makedirs(os.environ["TAGESFORM_DATA_DIR"], exist_ok=True)
    atexit.register(shutil.rmtree, _tmp, True)

    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["OPEN_WEATHER_API_KEY"] = "test-openweather-key"
    os.environ["OPEN_WEATHER_CITY"] = "Testville"
    os.environ["NEWS_API_KEY"] = "test-news-key"
    os.environ["BBC_NEWS_TRUST"] = "0.5"
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # deliberately unreachable
    os.environ["OLLAMA_MODEL"] = "test-model"
