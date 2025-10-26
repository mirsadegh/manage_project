# Your Project Name

Brief description of your Django project.

## Setup

1. Clone the repository
```bash

git clone https://github.com/mirsadegh/manage_project.git
cd manage_project
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your settings
```

5. Run migrations
```bash
python manage.py migrate
```

6. Create superuser
```bash
python manage.py createsuperuser
```

7. Run development server
```bash
python manage.py runserver
```

## Technologies Used

- Django
- PostgreSQL
- [Other technologies]