import unittest
import os

from app import create_app
from db import get_db, query


class DatabaseFallbackTests(unittest.TestCase):
    def test_sqlite_fallback_initializes_schema(self):
        app = create_app()
        app.config.update(
            TESTING=os.environ.get('FLASK_TESTING', 'true').lower() == 'true',
            MYSQL_HOST=os.environ.get('MYSQL_HOST', '127.0.0.1'),
            MYSQL_USER=os.environ.get('MYSQL_USER', 'root'),
            MYSQL_PASSWORD=os.environ.get('MYSQL_PASSWORD_WRONG', 'invalid-password-forces-sqlite-fallback'),
            MYSQL_DB=os.environ.get('MYSQL_DB', 'salon_db'),
        )

        with app.app_context():
            db = get_db()
            self.assertIsNotNone(db)
            tables = query("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            self.assertTrue(tables)


if __name__ == '__main__':
    unittest.main()
