from flask import Flask, render_template, session, redirect, url_for, current_app
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
from config import Config
from db import close_db
import os

socketio = SocketIO()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    app.config['WTF_CSRF_ENABLED'] = True

    # Init Socket.IO — use gevent on Render, threading locally
    try:
        import gevent  # noqa
        _async_mode = 'gevent'
    except ImportError:
        _async_mode = 'threading'
    socketio.init_app(
        app,
        cors_allowed_origins='*',
        async_mode=_async_mode,
        logger=False,
        engineio_logger=False,
        manage_session=False
    )
    csrf.init_app(app)

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.before_request
    def check_maintenance():
        from db import query
        # Allow: admin users, login/logout routes, static files, ping
        allowed_endpoints = {'auth.login', 'auth.logout', 'static', 'ping'}
        if request.endpoint in allowed_endpoints:
            return
        if session.get('is_admin'):
            return
        try:
            row = query("SELECT value FROM settings WHERE `key`='maintenance_mode'", one=True)
            if row and row['value'] == '1':
                from flask import render_template
                wa = query("SELECT value FROM settings WHERE `key`='whatsapp_number'", one=True)
                phone = query("SELECT value FROM settings WHERE `key`='shop_phone'", one=True)
                return render_template('maintenance.html',
                    whatsapp=wa['value'] if wa else '',
                    phone=phone['value'] if phone else ''), 503
        except Exception:
            pass

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
        today_offers = []
        try:
            from datetime import date
            today = date.today().isoformat()
            today_offers = query(
                "SELECT * FROM offers WHERE is_active=1 AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
                (today, today)
            )
        except Exception as e:
            current_app.logger.warning('today_offers query failed: %s', e)
        return dict(
            pending_appts=pending_appts,
            today_offers=today_offers,
            now_date=__import__('datetime').date.today().isoformat(),
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
    from routes.calendar_api import cal_api
    app.register_blueprint(auth)
    app.register_blueprint(customer)
    app.register_blueprint(admin)
    app.register_blueprint(cal_api)
    # Calendar API uses JSON + session auth — exempt from CSRF form token check
    try:
        from flask_wtf.csrf import exempt as csrf_exempt
        csrf_exempt(cal_api)
    except Exception:
        pass
    csrf.exempt(cal_api)

    @app.route('/ping')
    def ping():
        return 'ok', 200

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

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

    # ── Socket.IO events ──────────────────────────────────────────────────────
    @socketio.on('connect')
    def on_connect():
        emit('connected', {'status': 'ok'})

    @socketio.on('ping_calendar')
    def on_ping():
        emit('pong_calendar', {'ts': __import__('datetime').datetime.now().isoformat()})

    return app


if __name__ == '__main__':
    app = create_app()
    socketio.run(
        app,
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        allow_unsafe_werkzeug=True
    )
