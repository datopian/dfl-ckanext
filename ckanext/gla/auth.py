import logging
import os
import re
import string
from typing import Any

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.orm.attributes import flag_modified

import ckan.lib.navl.dictization_functions as df
from ckan import authz, model
from ckan.common import _
from ckan.types import Context, FlattenDataDict, FlattenErrorDict, FlattenKey

logger = logging.getLogger(__name__)


SECRET_KEY = os.environ.get("SECURE_TOKEN_GENERATION_SECURITY_KEY")

def _requester_is_sysadmin(context):
    requester = context.get("user", None)
    return authz.is_sysadmin(requester)


def _requester_is_manager(context):
    requester = context.get("user", None)
    return authz.has_user_permission_for_some_org(requester, "manage_group")


def user_list(context, data_dict=None):
    """Only sysadmins should be allowed to view the full list of users"""
    return {
        "success": _requester_is_sysadmin(context) or _requester_is_manager(context)
    }

def user_show(context, data_dict=None):
    """sysadmins can view all user profiles.
    If not a sysadmin, a user can only view their own profile.
    Based on: https://github.com/qld-gov-au/ckanext-qgov/blob/master/ckanext/qgov/common/auth_functions.py#L126
    """
    if _requester_is_sysadmin(context) or _requester_is_manager(context):
        return {"success": True}
    requester = context.get("user")
    id = data_dict.get("id", None)
    if id:
        user_obj = model.User.get(id)
    else:
        user_obj = data_dict.get("user_obj", None)
    if user_obj:
        return {"success": requester in [user_obj.name, user_obj.id]}

    return {"success": False}


def is_email_verified(user_obj: model.User) -> bool:
    if user_obj.plugin_extras:
        return (
            user_obj.plugin_extras.get("gla", {}).get("verified_email", False)
            == user_obj.email.lower()
        )
    else:
        return False
