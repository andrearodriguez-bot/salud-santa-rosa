"""Prototipo complementario para consulta de servicios de salud.

Los registros de demostración son ficticios. No usar para orientar desplazamientos
reales hasta verificar la información con las entidades competentes.
"""
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-key"),
        DATABASE=os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "salud_santa_rosa.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS centers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            guidance TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
            source TEXT NOT NULL DEFAULT 'Dato de demostración; verificar antes de publicar'
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            center_id INTEGER NOT NULL REFERENCES centers(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
            day INTEGER NOT NULL CHECK(day BETWEEN 0 AND 6),
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            CHECK(start_time < end_time)
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 1,
            description TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );
        """)
        db.commit()

    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    @app.context_processor
    def inject_csrf():
        return {"csrf_token": csrf_token}

    @app.before_request
    def protect_post():
        if request.method == "POST":
            submitted = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not secrets.compare_digest(submitted, expected):
                abort(400, description="Token de seguridad inválido. Recargue el formulario.")

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("admin_id"):
                return redirect(url_for("login", next=request.path))
            return fn(*args, **kwargs)
        return wrapped

    def valid_time(value):
        try:
            datetime.strptime(value, "%H:%M")
            return True
        except (TypeError, ValueError):
            return False

    def validate_schedule(day, start, end):
        errors = []
        try:
            d = int(day)
            if d < 0 or d > 6:
                errors.append("El día debe estar entre 0 (lunes) y 6 (domingo).")
        except (TypeError, ValueError):
            errors.append("El día debe ser un número entre 0 y 6.")
        if not valid_time(start) or not valid_time(end):
            errors.append("Las horas deben tener formato HH:MM.")
        elif start >= end:
            errors.append("La hora de inicio debe ser anterior a la hora de cierre.")
        return errors

    @app.route("/")
    def index():
        term = request.args.get("q", "").strip()[:60]
        db = get_db()
        if term:
            rows = db.execute("""SELECT DISTINCT c.* FROM centers c
                LEFT JOIN services s ON s.center_id=c.id
                WHERE c.name LIKE ? OR s.name LIKE ? ORDER BY c.name""",
                (f"%{term}%", f"%{term}%")).fetchall()
        else:
            rows = db.execute("SELECT * FROM centers ORDER BY name").fetchall()
        return render_template("index.html", centers=rows, term=term)

    @app.route("/centro/<int:center_id>")
    def center_detail(center_id):
        db = get_db()
        center = db.execute("SELECT * FROM centers WHERE id=?", (center_id,)).fetchone()
        if center is None:
            abort(404)
        services = db.execute("SELECT * FROM services WHERE center_id=? ORDER BY name", (center_id,)).fetchall()
        details = []
        days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        for service in services:
            schedules = db.execute("SELECT * FROM schedules WHERE service_id=? ORDER BY day,start_time", (service["id"],)).fetchall()
            requirements = db.execute("SELECT * FROM requirements WHERE service_id=? ORDER BY position,id", (service["id"],)).fetchall()
            details.append({"service": service, "schedules": schedules, "requirements": requirements, "days": days})
        return render_template("center.html", center=center, details=details)

    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()[:80]
            password = request.form.get("password", "")
            admin = get_db().execute(
                "SELECT * FROM admins WHERE username=?",
                (username,)
            ).fetchone()

            if admin and check_password_hash(admin["password_hash"], password):
                session.clear()
                session["admin_id"] = admin["id"]
                session["admin_name"] = admin["username"]
                csrf_token()
                return redirect(url_for("dashboard"))

            flash("Usuario o contraseña incorrectos.", "error")

        return render_template("login.html")

    @app.route("/admin/logout", methods=["POST"])
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/admin")
    @login_required
    def dashboard():
        db = get_db()
        centers = db.execute("SELECT * FROM centers ORDER BY name").fetchall()
        services = db.execute("SELECT s.*,c.name AS center_name FROM services s JOIN centers c ON c.id=s.center_id ORDER BY c.name,s.name").fetchall()
        schedules = db.execute("SELECT h.*,s.name AS service_name FROM schedules h JOIN services s ON s.id=h.service_id ORDER BY s.name,h.day,h.start_time").fetchall()
        requirements = db.execute("SELECT r.*,s.name AS service_name FROM requirements r JOIN services s ON s.id=r.service_id ORDER BY s.name,r.position").fetchall()
        return render_template("dashboard.html", centers=centers, services=services, schedules=schedules, requirements=requirements)

    @app.route("/admin/centro/nuevo", methods=["POST"])
    @login_required
    def add_center():
        name = request.form.get("name", "").strip()[:150]
        if not name:
            flash("El nombre del centro es obligatorio.", "error")
            return redirect(url_for("dashboard"))
        db = get_db()
        db.execute("INSERT INTO centers(name,address,phone,guidance,updated_at,verified,source) VALUES(?,?,?,?,?,0,?)",
                   (name, request.form.get("address", "").strip()[:250], request.form.get("phone", "").strip()[:60],
                    request.form.get("guidance", "").strip()[:500], datetime.now().strftime("%Y-%m-%d"),
                    request.form.get("source", "Pendiente de verificación").strip()[:250] or "Pendiente de verificación"))
        db.commit()
        flash("Centro creado. Su información queda pendiente de verificación.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/centro/<int:center_id>/editar", methods=["POST"])
    @login_required
    def edit_center(center_id):
        db = get_db()
        if not db.execute("SELECT id FROM centers WHERE id=?", (center_id,)).fetchone(): abort(404)
        name = request.form.get("name", "").strip()[:150]
        if not name:
            flash("El nombre del centro es obligatorio.", "error")
            return redirect(url_for("dashboard"))
        db.execute("UPDATE centers SET name=?,address=?,phone=?,guidance=?,updated_at=?,verified=0,source=? WHERE id=?",
                   (name, request.form.get("address", "").strip()[:250], request.form.get("phone", "").strip()[:60],
                    request.form.get("guidance", "").strip()[:500], datetime.now().strftime("%Y-%m-%d"),
                    request.form.get("source", "Pendiente de verificación").strip()[:250], center_id))
        db.commit()
        flash("Centro actualizado y marcado nuevamente como pendiente de verificación.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/centro/<int:center_id>/eliminar", methods=["POST"])
    @login_required
    def delete_center(center_id):
        db = get_db()
        db.execute("DELETE FROM centers WHERE id=?", (center_id,))
        db.commit()
        flash("Centro eliminado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/centro/<int:center_id>/verificar", methods=["POST"])
    @login_required
    def verify_center(center_id):
        source = request.form.get("source", "").strip()[:250]
        if not source:
            flash("Indique la fuente oficial consultada antes de verificar.", "error")
            return redirect(url_for("dashboard"))
        db = get_db()
        db.execute("UPDATE centers SET verified=1,source=?,updated_at=? WHERE id=?",
                   (source, datetime.now().strftime("%Y-%m-%d"), center_id))
        db.commit()
        flash("Estado de verificación actualizado. Conserve el soporte de la fuente consultada.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/servicio/nuevo", methods=["POST"])
    @login_required
    def add_service():
        name = request.form.get("name", "").strip()[:150]
        center_id = request.form.get("center_id", type=int)
        if not name or not center_id:
            flash("Seleccione un centro e indique el nombre del servicio.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO services(center_id,name,description) VALUES(?,?,?)",
                       (center_id, name, request.form.get("description", "").strip()[:500]))
            db.commit()
            flash("Servicio creado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/servicio/<int:service_id>/editar", methods=["POST"])
    @login_required
    def edit_service(service_id):
        name = request.form.get("name", "").strip()[:150]
        if not name:
            flash("El nombre del servicio es obligatorio.", "error")
        else:
            db = get_db()
            db.execute("UPDATE services SET name=?,description=? WHERE id=?",
                       (name, request.form.get("description", "").strip()[:500], service_id))
            db.commit()
            flash("Servicio actualizado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/servicio/<int:service_id>/eliminar", methods=["POST"])
    @login_required
    def delete_service(service_id):
        db = get_db()
        db.execute("DELETE FROM services WHERE id=?", (service_id,))
        db.commit()
        flash("Servicio eliminado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/horario/nuevo", methods=["POST"])
    @login_required
    def add_schedule():
        service_id = request.form.get("service_id", type=int)
        day = request.form.get("day", "")
        start = request.form.get("start_time", "")
        end = request.form.get("end_time", "")
        errors = validate_schedule(day, start, end)
        if not service_id:
            errors.append("Seleccione un servicio.")
        if errors:
            for error in errors: flash(error, "error")
        else:
            db = get_db()
            db.execute("INSERT INTO schedules(service_id,day,start_time,end_time) VALUES(?,?,?,?)",
                       (service_id, int(day), start, end))
            db.execute("UPDATE centers SET updated_at=?,verified=0 WHERE id=(SELECT center_id FROM services WHERE id=?)",
                       (datetime.now().strftime("%Y-%m-%d"), service_id))
            db.commit()
            flash("Horario registrado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/horario/<int:schedule_id>/editar", methods=["POST"])
    @login_required
    def edit_schedule(schedule_id):
        day = request.form.get("day", "")
        start = request.form.get("start_time", "")
        end = request.form.get("end_time", "")
        errors = validate_schedule(day, start, end)
        if errors:
            for error in errors: flash(error, "error")
        else:
            db = get_db()
            db.execute("UPDATE schedules SET day=?,start_time=?,end_time=? WHERE id=?",
                       (int(day), start, end, schedule_id))
            db.commit()
            flash("Horario actualizado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/horario/<int:schedule_id>/eliminar", methods=["POST"])
    @login_required
    def delete_schedule(schedule_id):
        db = get_db()
        db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        db.commit()
        flash("Horario eliminado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/requisito/nuevo", methods=["POST"])
    @login_required
    def add_requirement():
        service_id = request.form.get("service_id", type=int)
        description = request.form.get("description", "").strip()[:500]
        if not service_id or not description:
            flash("Seleccione un servicio e indique el requisito.", "error")
        else:
            db = get_db()
            position = db.execute("SELECT COALESCE(MAX(position),0)+1 AS p FROM requirements WHERE service_id=?", (service_id,)).fetchone()["p"]
            db.execute("INSERT INTO requirements(service_id,position,description) VALUES(?,?,?)", (service_id, position, description))
            db.commit()
            flash("Requisito registrado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/requisito/<int:req_id>/editar", methods=["POST"])
    @login_required
    def edit_requirement(req_id):
        description = request.form.get("description", "").strip()[:500]
        if not description:
            flash("El requisito no puede quedar vacío.", "error")
        else:
            db = get_db()
            db.execute("UPDATE requirements SET description=? WHERE id=?", (description, req_id))
            db.commit()
            flash("Requisito actualizado.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/admin/requisito/<int:req_id>/eliminar", methods=["POST"])
    @login_required
    def delete_requirement(req_id):
        db = get_db()
        db.execute("DELETE FROM requirements WHERE id=?", (req_id,))
        db.commit()
        flash("Requisito eliminado.", "success")
        return redirect(url_for("dashboard"))

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Base de datos creada.")

    @app.cli.command("create-admin")
    def create_admin_command():
        import getpass
        username = input("Usuario administrador: ").strip()
        password = getpass.getpass("Contraseña (mínimo 12 caracteres): ")
        if len(password) < 12:
            raise SystemExit("La contraseña debe tener al menos 12 caracteres.")
        init_db()
        db = get_db()
        db.execute("""
    INSERT INTO admins(username, password_hash)
    VALUES(?, ?)
    ON CONFLICT(username)
    DO UPDATE SET password_hash = excluded.password_hash
""", (username, generate_password_hash(password)))
        db.commit()
        print("Administrador creado.")

    with app.app_context():
        init_db()

    return app


app = create_app()
