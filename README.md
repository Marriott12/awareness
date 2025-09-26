# Awareness Web Portal

A web-based dashboard for soldiers to access training modules on social media risks, take quizzes on the Cybersecurity Act, and review real-world OPSEC breach case studies.

## Features
- User authentication (login, registration, password reset)
- Dashboard landing page
- Training modules (interactive content)
- Quizzes (with scoring and feedback)
- Real-world case studies
- Admin panel for content management

## Stack
- Backend: Django (Python)
- Frontend: HTML, CSS, JavaScript
- Database: SQLite (development), PostgreSQL/MySQL (production)

## Setup
1. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
2. Run migrations:
   ```sh
   python manage.py migrate
   ```
3. Create a superuser:
   ```sh
   python manage.py createsuperuser
   ```
   If you want to create an admin account non-interactively (Windows PowerShell), you can run:

    ```powershell
    python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); User.objects.create_superuser('admin','admin@example.com','Admin2025')"
    ```
   Note: Storing plaintext passwords in code or repos is insecure. Use the command above only in a secure environment and rotate the password for production.
4. Start the development server:
   ```sh
   python manage.py runserver
   ```

## Deployment
- Use Gunicorn/uWSGI with Nginx for production.
- Configure environment variables for security.
- Use HTTPS.

## Environment Variables
- `AWARENESS_SECRET_KEY`: Django secret key (required, production only)
- `AWARENESS_DEBUG`: Set to `False` in production, `True` for development
- `AWARENESS_ALLOWED_HOSTS`: Comma-separated list of allowed hosts (e.g. `localhost,127.0.0.1,example.com`)
- `DATABASE_URL`: (Optional) Full database URL for production (e.g. `postgres://user:pass@host:5432/dbname`)
- `AWARENESS_ADMIN_DASHBOARD`: (Optional) URL name for admin dashboard redirect (default: `dashboard:admin`)
- `AWARENESS_SOLDIER_DASHBOARD`: (Optional) URL name for soldier dashboard redirect (default: `dashboard:home`)
- `DEFAULT_FROM_EMAIL`: (Optional) Email address for outgoing mail

## Linting & Formatting
- Run `python -m flake8` for lint checks.
- Run `black .` to auto-format code.

## Docker
- Build and run with Docker Compose:
   ```powershell
   docker compose up --build
   ```

## CI/CD
- GitHub Actions runs tests, lint, and Docker build on push.

---

Replace this README with more detailed documentation as the project evolves.
