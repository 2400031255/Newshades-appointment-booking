# LuxeSalon – Appointment Booking Web App

A modern, responsive salon appointment booking web application built with Flask, MySQL, and Bootstrap 5. Customers can browse services, select appointments, and send booking requests directly via WhatsApp.

---

## Features

- Customer signup & login (bcrypt password hashing)
- Browse & filter salon services
- Select multiple services
- Choose preferred date & time slot
- Auto-generated WhatsApp booking message
- Appointment history for customers
- Admin dashboard (manage services, view appointments & customers)
- Responsive design (mobile, tablet, desktop)
- Black, white & gold salon theme

---

## Tech Stack

| Layer      | Technology              |
|------------|-------------------------|
| Backend    | Python 3.10+ / Flask    |
| Database   | MySQL                   |
| Frontend   | Bootstrap 5, Vanilla JS |
| Auth       | bcrypt + Flask sessions |
| Booking    | WhatsApp wa.me API      |

---

## Project Structure

```
salon_app/
├── app.py               # Flask app factory & main routes
├── config.py            # Configuration (DB, WhatsApp number)
├── db.py                # Database helper functions
├── schema.sql           # Database schema + seed data
├── requirements.txt
├── .env.example
├── routes/
│   ├── auth.py          # Login, signup, logout
│   ├── customer.py      # Dashboard, booking, profile
│   └── admin.py         # Admin panel routes
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html
    ├── index.html
    ├── about.html
    ├── gallery.html
    ├── contact.html
    ├── auth/
    │   ├── login.html
    │   └── signup.html
    ├── customer/
    │   ├── dashboard.html
    │   ├── confirm.html
    │   ├── appointments.html
    │   └── profile.html
    └── admin/
        ├── base_admin.html
        ├── dashboard.html
        ├── services.html
        ├── service_form.html
        ├── appointments.html
        └── customers.html
```

---

## Setup Instructions

### 1. Prerequisites

- Python 3.10+
- MySQL 8.0+
- pip

### 2. Clone / Navigate to Project

```bash
cd salon_app
```

### 3. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```
SECRET_KEY=your-secret-key
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=salon_db
WHATSAPP_NUMBER=919876543210   # Your WhatsApp Business number (no + or spaces)
```

### 6. Set Up Database

Log into MySQL and run the schema:

```bash
mysql -u root -p < schema.sql
```

Or manually:

```sql
SOURCE /path/to/salon_app/schema.sql;
```

### 7. Run the Application

```bash
python app.py
```

Visit: **http://localhost:5000**

---

## Default Admin Login

Set up your admin credentials directly in the database after running `schema.sql`.
Update the password hash using bcrypt before going live.

> **Important:** Never commit real credentials to version control.

---

## WhatsApp Configuration

1. Open `config.py` or `.env`
2. Set `WHATSAPP_NUMBER` to your WhatsApp Business number
3. Format: country code + number, no spaces or `+` (e.g., `919876543210` for India)

When a customer books, the app opens:
```
https://wa.me/919876543210?text=<pre-filled message>
```

---

## Customization

| What to change         | Where                          |
|------------------------|--------------------------------|
| Salon name             | `base.html` – search "LuxeSalon" |
| WhatsApp number        | `.env` → `WHATSAPP_NUMBER`     |
| Address / phone        | `base.html` footer, `contact.html` |
| Working hours          | `base.html` footer             |
| Services               | Admin panel → Services         |
| Gallery images         | `static/images/` + `gallery.html` |
| Color theme            | `static/css/style.css` → `:root` variables |

---

## Production Deployment

For production, use Gunicorn + Nginx:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 "app:create_app()"
```

Set `debug=False` and use a strong `SECRET_KEY`.
