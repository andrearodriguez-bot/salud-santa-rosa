# Prototipo complementario – Consulta de servicios de salud en Santa Rosa de Ubalá

**Estado:** código fuente preparado a partir de los requisitos descritos en el documento académico. La aplicación no ha sido desplegada en un servidor público ni probada con habitantes. Los datos semilla y los datos que se ingresen para demostración deben tratarse como ficticios hasta su verificación institucional.

## Requisitos
- Python 3.10 o superior.
- Flask 3.1.2 (instalable con `pip install -r requirements.txt`).
- Navegador actualizado.

## Instalación local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Defina una clave secreta propia antes de ejecutar la aplicación:

```bash
# Linux/macOS
export SECRET_KEY="reemplace-por-una-clave-aleatoria-larga"
# Windows PowerShell
$env:SECRET_KEY="reemplace-por-una-clave-aleatoria-larga"
```

Cree un administrador interactivo (la contraseña no queda escrita en el repositorio):

```bash
flask --app app:create_app create-admin
```

Ejecute el servidor local:

```bash
flask --app app:create_app run --debug
```

Abra `http://127.0.0.1:5000`. Para un despliegue real, desactive el modo debug, use HTTPS, configure `COOKIE_SECURE=1`, establezca una clave secreta robusta y aplique revisión de seguridad.

## Funcionalidades incluidas en este prototipo complementario
- Consulta pública de centros, servicios, horarios y requisitos.
- Búsqueda parametrizada por nombre de centro o servicio.
- Acceso administrativo con hash de contraseña.
- Protección CSRF para formularios POST.
- Gestión de centros (crear, editar y eliminar).
- Gestión de servicios (crear, editar y eliminar).
- Registro y eliminación de horarios con validación de día y rango horario.
- Registro y eliminación de requisitos.
- Estado de verificación de la información y fuente consultada; cualquier edición vuelve a dejar el centro como pendiente.
- Aviso visible de que la herramienta informa y no asigna citas.

## Alcance y limitaciones
Este repositorio es una implementación complementaria construida desde las especificaciones del PDF recibido. No se ha comprobado que sea el mismo código descrito originalmente por la estudiante. No contiene datos reales confirmados de centros de salud. No incorpora aún pruebas de usuario, despliegue HTTPS ni auditoría externa de seguridad. Antes de usarlo con la comunidad se requiere revisión técnica, carga de información oficial y validación por personal autorizado.

## Pruebas
Ejecute `pytest -q`. El archivo `tests/test_app.py` contiene pruebas básicas de acceso, CSRF, consulta y validación de horarios. El entorno en el que se generó este paquete no tenía Flask instalado y no permitió descargar dependencias; por ello, las pruebas no se han ejecutado aquí. Deben ejecutarse en un equipo con dependencias instaladas y anexar la salida real de consola.

## Modelo de datos
Cinco tablas: `centers`, `services`, `schedules`, `requirements` y `admins`. Se usan claves foráneas y restricciones `CHECK` para el rango de días y la relación entre horas.
