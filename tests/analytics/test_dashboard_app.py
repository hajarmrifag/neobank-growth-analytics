from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"


def test_dashboard_renders_without_errors():
    app = AppTest.from_file(str(APP), default_timeout=30).run()

    assert not app.exception
    assert app.title[0].value == "Neobank Growth & Unit Economics Analytics"
    assert len(app.metric) >= 8
