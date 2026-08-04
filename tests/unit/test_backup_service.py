import os
import pytest

from app.services.backup_service import BackupService

pytestmark = pytest.mark.unit


def test_resolve_sqlite_path_uses_instance_folder_for_relative_uri(app):
    """Regression test: Flask-SQLAlchemy resolves a relative
    `sqlite:///path` URI against the app's instance folder, not the
    process's current working directory -- backups were failing with
    "No such file or directory" because this used to join against
    os.getcwd() instead, landing on a path that doesn't exist."""
    with app.app_context():
        service = BackupService(db_uri='sqlite:///tagesform.db')
        resolved = service._resolve_sqlite_path()

    assert resolved == os.path.join(app.instance_path, 'tagesform.db')


def test_resolve_sqlite_path_passes_through_absolute_uri_unchanged(app):
    with app.app_context():
        if os.name == 'nt':
            abs_uri = 'sqlite:///C:/data/tagesform.db'
            expected = 'C:/data/tagesform.db'
        else:
            abs_uri = 'sqlite:////var/data/tagesform.db'
            expected = '/var/data/tagesform.db'

        service = BackupService(db_uri=abs_uri)
        resolved = service._resolve_sqlite_path()

    assert resolved == expected
