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

---

Replace this README with more detailed documentation as the project evolves.
