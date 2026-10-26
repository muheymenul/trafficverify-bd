# TrafficVerify BD (DEMO)

An **educational demonstration project** inspired by vehicle and driving-licence verification workflows used by traffic police.

> **This is NOT an official Bangladesh Police or BRTA application.** It has no access to any real database. All records (police, vehicles, drivers, licences) are **fictional demo data**. A match in this system does **not** mean a vehicle or licence is legally valid in Bangladesh.

## Features

- Two-step police officer registration (Demo Police ID + hashed one-time code)
- Login, logout, password change and password reset
- Role-based access: Administrator and Police Officer (checked on the server)
- Vehicle and driving-licence search with Valid / Expired / Invalid / Unverified results
- Audit log of every search (read-only, cannot be edited or deleted)
- Custom Admin Dashboard with search, filters and pagination
- Django Admin with CSV import (all-or-nothing, with validation) and export
- Demo data generator (100 police, 100 vehicles, 100 drivers/licences)
- Automated tests, responsive Bootstrap 5 interface

## Tech stack

Python, Django, SQLite (development), Bootstrap 5, JavaScript, Pillow.

## Setup (Windows)

```powershell
git clone https://github.com/YOUR-USERNAME/trafficverify-bd.git
cd trafficverify-bd
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Generate a secret key and put it in `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py generate_demo_data
python manage.py runserver
```

Open http://127.0.0.1:8000/. Registration codes for demo officers are saved in `demo_output/police_registration_codes.csv` (not committed to Git).

## Run the tests

```powershell
python manage.py test
```

## Security notes

- Secrets live in `.env` (excluded from Git).
- Passwords and registration codes are stored hashed.
- Console email backend is for development only; it does not send real email.
- Production needs `DJANGO_DEBUG=False`, HTTPS, a real database and a real email service.

## Screenshots

Add your own screenshots to a `screenshots/` folder and link them here.

## Disclaimer

Educational portfolio project. Fictional data only. Not affiliated with Bangladesh Police or BRTA.