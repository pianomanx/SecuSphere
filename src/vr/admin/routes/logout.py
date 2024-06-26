from flask_login import logout_user, login_required
from flask import session, redirect, url_for
from vr.admin import admin
from vr import app


NAV_CAT= { "name": "Admin", "url": "admin.admin_dashboard"}


if app.config['AUTH_TYPE'] == 'local':
    @admin.route('/logout')
    @login_required
    def logout():
        logout_user()
        del session['username']
        return redirect(url_for('admin.login'))
elif app.config['AUTH_TYPE'] == 'azuread':
    @admin.route('/logout')
    def logout():
        logout_user()
        session.clear()  # Wipe out user and its token cache from session
        return redirect(url_for('admin.login'))
