import re
import pytest
from app import create_app
from werkzeug.security import generate_password_hash
from flask import current_app

@pytest.fixture()
def app(tmp_path):
    db = tmp_path / "test.sqlite3"
    app = create_app({"TESTING": True, "SECRET_KEY": "test-key", "DATABASE": str(db), "SESSION_COOKIE_SECURE": False})
    with app.app_context():
        conn = current_app.config
    yield app

@pytest.fixture()
def client(app):
    return app.test_client()

def get_token(client):
    response = client.get("/admin/login")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match
    return match.group(1)

def login_as_admin(client):
    with client.session_transaction() as sess:
        sess["admin_id"] = 1
        sess["admin_name"] = "admin_test"
    return get_token(client)

def test_home_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Consulta de centros" in response.data

def test_admin_requires_login(client):
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]

def test_post_without_csrf_is_rejected(client):
    response = client.post("/admin/login", data={"username": "x", "password": "y"})
    assert response.status_code == 400

def test_login_rejects_unknown_user(client):
    token = get_token(client)
    response = client.post("/admin/login", data={"csrf_token": token, "username": "nobody", "password": "wrong"})
    assert response.status_code == 200
    assert "incorrectos" in response.get_data(as_text=True)

def test_center_create_requires_admin(client):
    token = get_token(client)
    response = client.post("/admin/centro/nuevo", data={"csrf_token": token, "name": "Centro de prueba"})
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]

def test_center_crud_and_verification(client):
    token = login_as_admin(client)
    response = client.post("/admin/centro/nuevo", data={"csrf_token": token, "name": "Centro ficticio", "source": "Dato de prueba"})
    assert response.status_code == 302
    with client.application.app_context():
        row = current_app.extensions.get("unused")
        import sqlite3
        db = sqlite3.connect(current_app.config["DATABASE"])
        center_id = db.execute("SELECT id FROM centers WHERE name='Centro ficticio'").fetchone()[0]
        db.close()
    token = get_token(client)
    response = client.post(f"/admin/centro/{center_id}/verificar", data={"csrf_token": token, "source": "Fuente oficial simulada para prueba"})
    assert response.status_code == 302
    response = client.get(f"/centro/{center_id}")
    assert b"Informaci\xc3\xb3n verificada" in response.data
    token = get_token(client)
    response = client.post(f"/admin/centro/{center_id}/eliminar", data={"csrf_token": token})
    assert response.status_code == 302
    assert client.get(f"/centro/{center_id}").status_code == 404

def test_schedule_validation_and_public_display(client):
    token = login_as_admin(client)
    client.post("/admin/centro/nuevo", data={"csrf_token": token, "name": "Centro horario"})
    with client.application.app_context():
        import sqlite3
        db = sqlite3.connect(current_app.config["DATABASE"])
        center_id = db.execute("SELECT id FROM centers WHERE name='Centro horario'").fetchone()[0]
        db.execute("INSERT INTO services(center_id,name) VALUES(?,?)", (center_id, "Medicina general"))
        service_id = db.execute("SELECT id FROM services WHERE center_id=?", (center_id,)).fetchone()[0]
        db.commit(); db.close()
    token = get_token(client)
    bad = client.post("/admin/horario/nuevo", data={"csrf_token": token, "service_id": service_id, "day": 1, "start_time": "17:00", "end_time": "08:00"})
    assert bad.status_code == 302
    with client.application.app_context():
        import sqlite3
        db = sqlite3.connect(current_app.config["DATABASE"])
        assert db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0] == 0
        db.close()
    token = get_token(client)
    good = client.post("/admin/horario/nuevo", data={"csrf_token": token, "service_id": service_id, "day": 1, "start_time": "08:00", "end_time": "12:00"})
    assert good.status_code == 302
    page = client.get(f"/centro/{center_id}")
    assert b"Medicina general" in page.data
    assert b"08:00" in page.data
