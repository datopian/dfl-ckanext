import logging
import os
from os.path import exists
from typing import Any, cast

import ckan
import ckan.lib.base as base
import ckan.lib.helpers as h
import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan import authz
from ckan.common import _, current_user, g
from ckan.types import Context
from flask import Blueprint, send_file
from itsdangerous.exc import SignatureExpired, BadData
from . import auth, email
log = logging.getLogger(__name__)

favourites = Blueprint("favourites_blueprint", __name__)
users = Blueprint("users_blueprint", __name__)
search_log_download = Blueprint("search_log_download_blueprint", __name__)
undelete = Blueprint("undelete_blueprint", __name__)

# Note this expiry time is measured in seconds
# Default is 2 days
EMAIL_VERIFICATION_TOKEN_EXPIRY = int(os.environ.get("EMAIL_VERIFICATION_TOKEN_EXPIRY","86400"))


def show_favourites():
    log.info("IN SHOW_FAVOURITES")
    # If an unregistered user ends up on the /dataset/following page
    # show them a message saying that they need to create an account
    if not tk.g.userobj:
        return h.redirect_to("user.login")

    data_dict: dict[str, Any] = {
        "id": id,
        "user_obj": tk.g.userobj,
    }

    context = {
        "model": model,
        "session": model.Session,
        "user": tk.g.user or tk.g.author,
        "for_view": True,
        "auth_user_obj": tk.g.userobj,
    }
    data_dict = {"id": tk.g.userobj.id}
    followed_datasets = tk.get_action("dataset_followee_list")(context, data_dict)
    log.info("GOT FOLLOWED DATASETS")
    extra_vars = _extra_template_variables(context, data_dict)
    extra_vars.update({"packages": followed_datasets})
    log.info(extra_vars)
    return tk.render("following.html", extra_vars)


favourites.add_url_rule(
    "/dashboard/following",
    methods=["GET"],
    view_func=show_favourites,
    endpoint="show_favourites",
)

## Users routes:


# Copied from:
# https://github.com/ckan/ckan/blob/3c676e3cf1f075c5e9bae3b625b86247edf3cc1d/ckan/views/user.py#L60
# and edited to catch NotAuthorized and NotFound together and return
# a 403 error for both, to avoid disclosure of usernames through enumeration
def _extra_template_variables(
    context: Context, data_dict: dict[str, Any]
) -> dict[str, Any]:
    is_sysadmin = False
    if current_user.is_authenticated:
        is_sysadmin = authz.is_sysadmin(current_user.name)
    try:
        user_dict = tk.get_action("user_show")(context, data_dict)
    # Catch NotAuthorized and NotFound and return 403 for both:
    except (logic.NotAuthorized, logic.NotFound) as e:
        base.abort(403, _("Not authorized to see this page"))

    is_myself = user_dict["name"] == current_user.name
    about_formatted = h.render_markdown(user_dict["about"])
    extra: dict[str, Any] = {
        "is_sysadmin": is_sysadmin,
        "user_dict": user_dict,
        "is_myself": is_myself,
        "about_formatted": about_formatted,
    }
    return extra

from . import user


# Copied from:
# https://github.com/ckan/ckan/blob/3c676e3cf1f075c5e9bae3b625b86247edf3cc1d/ckan/views/user.py#L124
#def view_user(id):
#    match id:
#        case "me":
#            return ckan.views.user.me()
#        case "edit":
#            return ckan.views.user._edit_view()
#        case "register":
#            return ckan.views.user.RegisterView.as_view("register")()
#        case "login":
#            return ckan.views.user.login()
#        case "_logout":
#            return ckan.views.user.logout()
#        case "logged_out_redirect":
#            return ckan.views.user.logged_out_page()
#        case "reset":
#            return ckan.views.user.RequestResetView.as_view("request_reset")()
#
#    context = cast(
#        Context,
#        {
#            "model": model,
#            "session": model.Session,
#            "user": current_user.name,
#            "auth_user_obj": current_user,
#            "for_view": True,
#        },
#    )
#    data_dict: dict[str, Any] = {
#        "id": id,
#        "user_obj": current_user,
#        "include_datasets": True,
#        "include_num_followers": True,
#    }
#    # FIXME: line 331 in multilingual plugins expects facets to be defined.
#    # any ideas?
#    g.fields = []
#
#    extra_vars = _extra_template_variables(context, data_dict)
#    return base.render("user/read.html", extra_vars)


#def verify_user(token, expiration=EMAIL_VERIFICATION_TOKEN_EXPIRY):
#    """
#    Verify a user's email address by checking that a GET request is made with a valid token.
#    """
#    # Has user already verified their email address?
#    # Was user redirected here?
#
#    try:
#        user_email = auth.verify_user(token, expiration=expiration)
#        if user_email:
#            h.flash_success("Your email address has been verified, please login to continue.")
#            return tk.redirect_to("user.login")
#        
#    except SignatureExpired as e:
#        user_email = auth.read_email_from_token(token,max_age=None)
#
#        user_obj = model.User.by_email(user_email)
#        if user_obj:
#            email.send_email_verification_link(user_obj)
#            h.flash_error("Your email verification link has expired. A new verification link has been sent to your email address, please check your inbox, and click it.")
#            return tk.redirect_to("user.login")
#        else:
#            # This case shouldn't normally happen, it would likely
#            # mean we had sent out a verification link, but did not
#            # have the corresponding account stored in our database.
#            h.flash_error("User account could not be found, please report this to an administrator")
#            return tk.redirect_to("user.login")
#
#    except BadData as ex:
#        log.error('Supplied verification link raised an error',ex)
#        
#        h.flash_error("The verification link you have supplied is invalid/untrusted; please try again or contact us.")
#        return tk.redirect_to("user.login")
#
#
#users.add_url_rule("/user/<id>", methods=["GET"], view_func=view_user)
#users.add_url_rule("/user/register", methods=["POST"], view_func=user.GlaRegisterView.as_view("register"))
#users.add_url_rule(
#    "/user/verify/<token>",
#    methods=["GET"],
#    view_func=verify_user,
#    endpoint="verify_email",
#)

## Download routes:

def get_server_search_logs():
    if not current_user.is_authenticated:
        base.abort(403, _("Not authorized to see this page"))

    if not authz.is_sysadmin(current_user.name):
        base.abort(403, _("Not authorized to see this page"))

    if not exists("/srv/app/search_logs.csv"):
        base.abort(404, _("Log file not found"))
    return send_file(
        "/srv/app/search_logs.csv", mimetype="text/csv", as_attachment=True
    )


search_log_download.add_url_rule(
    "/search_logs", methods=["GET"], view_func=get_server_search_logs
)


def undelete_package(id):
    res = tk.get_action("package_patch")(None, {"id": id, "state": "active"})
    return tk.redirect_to("dataset.read", id=id)


undelete.add_url_rule(
    "/dataset/<id>/undelete",
    methods=["POST"],
    view_func=undelete_package,
    endpoint="undelete_package",
)


lang_redirect = Blueprint("lang_redirect", __name__)

lang_redirect.add_url_rule(
    "/api/i18n/en-GB",
    view_func=lambda: tk.redirect_to("/api/i18n/en_GB"),
    endpoint="lang_redirect"
)

def get_blueprints():
    return [favourites, users, search_log_download, undelete, lang_redirect]
