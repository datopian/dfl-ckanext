import ckan.lib.mailer as Mailer
from ckan import model
from ckan.common import config
from ckan.lib.base import render
from ckan.lib.helpers import url_for

from . import auth


#def get_reset_link_html_body(user: model.User) -> str:
#    extra_vars = {
#        "reset_link": Mailer.get_reset_link(user),
#        "site_title": config.get("ckan.site_title"),
#        "site_url": config.get("ckan.site_url"),
#        "user_name": user.name,
#    }
#    return render("emails/reset_password.html", extra_vars)
#
#
## Override ckan's send_reset_link function to pass body_html into mail_user
## So that the password reset link email will be sent as multipart/alternative with both a plain text version and a html version
#def send_reset_link(user: model.User) -> None:
#    Mailer.create_reset_key(user)
#    body = Mailer.get_reset_link_body(user)
#    body_html = get_reset_link_html_body(user)
#    extra_vars = {"site_title": config.get("ckan.site_title")}
#    subject = render("emails/reset_password_subject.txt", extra_vars)
#
#    # Make sure we only use the first line
#    subject = subject.split("\n")[0]
#
#    Mailer.mail_user(user, subject, body, body_html)
#
#
#def send_email_verification_link(user_obj) -> None:
#    verification_link = config.get("ckan.site_url") + url_for(
#        "users_blueprint.verify_email", token=auth.generate_token(user_obj.email)
#    )
#    extra_vars = {
#        "verification_link": verification_link,
#        "site_title": config.get("ckan.site_title"),
#        "site_url": config.get("ckan.site_url"),
#        "user_name": user_obj.name,
#    }
#    body = render("emails/verify_email.html", extra_vars)
#
#    Mailer.mail_user(
#        recipient=user_obj,
#        subject="Greater London Authority Datastore: Verify email",
#        body=body,
#        body_html=body,
#    )
#
#def send_mfa_login_link(user_obj: model.User) -> None:
#    mfa_link = config.get("ckan.site_url") + url_for(
#        "user.login", token=auth.generate_mfa_login_token(user_obj.email)
#    )
#
#    extra_vars = {
#        "login_link_with_token": mfa_link,
#        "site_title": config.get("ckan.site_title"),
#        "site_url": config.get("ckan.site_url"),
#        "user_name": user_obj.name,
#    }
#    body = render("emails/login_link_email.html", extra_vars)
#    Mailer.mail_user(
#        recipient=user_obj,
#        subject="Greater London Authority Datastore: Login link",
#        body=body,
#        body_html=body,
#    )
