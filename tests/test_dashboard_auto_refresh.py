from pathlib import Path


def test_dashboard_refresh_controls_present():
    app_path = Path("dashboard/app.py")
    content = app_path.read_text(encoding="utf-8")
    assert 'st.button("Refresh now")' in content
    assert 'st.rerun()' in content
