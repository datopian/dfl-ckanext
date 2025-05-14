# encoding: utf-8
from __future__ import annotations

from typing import Any, Union

import ckan.lib.authenticator as authenticator
import ckan.lib.base as base
from ckan.common import (
    _,
    config,
    current_user,
    login_user,
    logout_user,
    request,
    session,
)
import ckan.plugins.toolkit as tk
import ckan.model as model
import ckan.lib.captcha as captcha

from ckan.lib.helpers import helper_functions as h
from ckan.types import Response
from ckan.views.user import next_page_or_default, rotate_token
from ckanext.gla import email
from ckanext.gla import auth
from itsdangerous.exc import SignatureExpired, BadData
import os


# measured in seconds
MFA_TOKEN_EXPIRY = int(os.environ.get("MFA_LOGIN_TOKEN_EXPIRY","300")) # default is 5 minutes

# Originally from:
# https://github.com/ckan/ckan/blob/9915ba0022b9a74a65e61c097b2fee584b044087/ckan/views/user.py#L521-L582
def login() -> Union[Response, str]:
    extra_vars: dict[str, Any] = {}

    if current_user.is_authenticated:
        return base.render("user/logout_first.html", extra_vars)

    if request.method == "POST":
        try:
            captcha.check_recaptcha(request)
        except captcha.CaptchaError:
            error_msg = _(u'Bad Captcha. Please try again.')
            h.flash_error(error_msg)
            return base.render("user/login.html", extra_vars)

        username_or_email = request.form.get("login")
        password = request.form.get("password")
        _remember = request.form.get("remember")

        identity = {
            u"login": username_or_email,
            u"password": password
        }

        user_obj = authenticator.ckan_authenticator(identity)
        if user_obj:
            next = request.args.get('next', request.args.get('came_from'))
            if _remember:
                from datetime import timedelta
                duration_time = timedelta(milliseconds=int(_remember))
                login_user(user_obj, remember=True, duration=duration_time)
                rotate_token()
                return next_page_or_default(next)
            else:
                email.send_mfa_login_link(user_obj)
                h.flash_success(u"We have emailed you a link to sign in")
                return base.render("user/login.html", {"display_mfa_token_message":True})
        else:
            err = _(u"Login failed. Bad username or password.")
            h.flash_error(err)
            return base.render("user/login.html", extra_vars)
    elif request.method == "GET" and request.args.get("token"):
        # Verify MFA flow
        token = request.args.get("token")
        try:
            user_email = auth.read_email_from_login_token(token,max_age=MFA_TOKEN_EXPIRY)
            user_obj = model.User.by_email(user_email)
            next = request.args.get('next', request.args.get('came_from'))

            login_user(user_obj, remember=True)

            rotate_token()

            success_msg = _(u"Welcome! You have been authenticated and logged in.")
            h.flash_success(success_msg)
            return next_page_or_default(next)

        except SignatureExpired as e:
            user_email = auth.read_email_from_login_token(token,max_age=None)

            user_obj = model.User.by_email(user_email)
            if user_obj:
                message = _(u"Your login link has expired.  Please try logging in again.")
                h.flash_error(message)

                return tk.redirect_to("user.login")

        except BadData as ex:
            err = _(u"Invalid Login Token - Please try logging in again.")
            h.flash_error(err)
            return tk.redirect_to("user.login")

    # Fallback and render login form
    return base.render("user/login.html", extra_vars)

## Originally from:
## https://github.com/ckan/ckan/blob/9915ba0022b9a74a65e61c097b2fee584b044087/ckan/views/user.py#L521-L582
##
## NOTE: we don't currently need to override logout, but if we do the
## code that goes with the above for logging in is here:
##
# def logout() -> Response:
#     user = current_user.name
#     if not user:
#         return h.redirect_to('user.login')
#
#     came_from = request.args.get('came_from', '')
#     logout_user()
#
#     field_name = config.get("WTF_CSRF_FIELD_NAME")
#     if session.get(field_name):
#         session.pop(field_name)
#
#     if h.url_is_local(came_from):
#         return h.redirect_to(str(came_from))
#
#     return h.redirect_to('user.logged_out_page')
