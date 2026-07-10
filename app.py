from flask import Flask, render_template, session, redirect, url_for, current_app
from config import Config
from db import close_db
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    app.config['WTF_CSRF_ENABLED'] = False

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_shop():
        from db import query
        def get_setting(key, default=''):
            try:
                row = query("SELECT value FROM settings WHERE `key`=%s", (key,), one=True)
                return row['value'] if row else default
            except Exception as e:
                current_app.logger.warning('get_setting(%s) failed: %s', key, e)
                return default
        pending_appts = 0
        if session.get('is_admin'):
            try:
                r = query("SELECT COUNT(*) as c FROM appointments WHERE status='Pending'", one=True)
                pending_appts = r['c'] if r else 0
            except Exception as e:
                current_app.logger.warning('pending_appts query failed: %s', e)
        return dict(
            pending_appts=pending_appts,
            shop={
                'name':           get_setting('shop_name', 'New Shades'),
                'phone':          get_setting('shop_phone', ''),
                'whatsapp':       get_setting('whatsapp_number', ''),
                'address':        get_setting('shop_address', ''),
                'hours_weekday':  get_setting('shop_hours_weekday', ''),
                'hours_saturday': get_setting('shop_hours_saturday', ''),
                'hours_sunday':   get_setting('shop_hours_sunday', ''),
            })

    from routes.auth import auth
    from routes.customer import customer
    from routes.admin import admin
    app.register_blueprint(auth)
    app.register_blueprint(customer)
    app.register_blueprint(admin)

    @app.route('/')
    def index():
        if session.get('user_id'):
            if session.get('is_admin'):
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('customer.dashboard'))
        from db import query
        try:
            reviews = query(
                "SELECT r.rating, r.comment, r.created_at, u.full_name FROM reviews r "
                "JOIN users u ON r.user_id=u.id ORDER BY r.created_at DESC LIMIT 6"
            )
        except Exception as e:
            app.logger.warning('reviews query failed: %s', e)
            reviews = []
        return render_template('index.html', reviews=reviews)

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact')
    def contact():
        from db import query
        def get_setting(key, default=''):
            try:
                row = query("SELECT value FROM settings WHERE `key`=%s", (key,), one=True)
                return row['value'] if row else default
            except Exception:
                return default
        shop = {
            'name':           get_setting('shop_name', 'New Shades'),
            'tagline':        get_setting('shop_tagline', 'Premium Salon & Studio'),
            'address':        get_setting('shop_address', ''),
            'phone':          get_setting('shop_phone', ''),
            'email':          get_setting('shop_email', ''),
            'hours_weekday':  get_setting('shop_hours_weekday', ''),
            'hours_saturday': get_setting('shop_hours_saturday', ''),
            'hours_sunday':   get_setting('shop_hours_sunday', ''),
            'whatsapp':       get_setting('whatsapp_number', ''),
            'map_embed':      get_setting('map_embed', ''),
        }
        return render_template('contact.html', shop=shop)

    @app.route('/services')
    def services():
        from db import query
        try:
            svcs = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
            categories = list(dict.fromkeys(s['category'] for s in svcs))
        except Exception:
            svcs, categories = [], []
        return render_template('services.html', services=svcs, categories=categories)

    @app.route('/gallery')
    def gallery():
        from db import query
        try:
            photos = query("SELECT * FROM gallery ORDER BY created_at DESC")
        except Exception:
            photos = []
        return render_template('gallery.html', photos=photos)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
