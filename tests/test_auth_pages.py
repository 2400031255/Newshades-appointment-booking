import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app


def test_auth_pages_do_not_render_csrf_tokens():
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()

    for endpoint in ["/login", "/signup"]:
        response = client.get(endpoint)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "csrf_token" not in html
        assert "name=\"csrf_token\"" not in html
