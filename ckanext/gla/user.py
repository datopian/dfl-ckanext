import ckan.lib.helpers as h
import ckan.lib.dictization.model_dictize as model_dictize
import ckan.model as model
from ckan.model.user import User
from ckan.model.group import Member, Group
from ckan.model.package import PackageMember

import ckan.plugins.toolkit as toolkit
from ckan.types import ActionResult

from ckan.common import asbool, logout_user, request
from ckan.types import Response
from ckan.views.user import RegisterView

import sqlalchemy as sa
from sqlalchemy.sql import exists

from .auth import is_email_verified


import ckan.logic as logic
import ckan.lib.base as base
from ckan import authz
from ckan.common import (
    _, config, g, current_user, login_user
)

from typing import Any, Optional, Union
import ckan.lib.captcha as captcha
import ckan.lib.navl.dictization_functions as dictization_functions

# The front end machinery only has the capacity to display one
# validation error per field. So this function roles multiple errors
# that might occur with e.g. the password policy into one combined
# error.
def clean_up_errors(e: logic.ValidationError):
    for k, v in e.error_dict.items():
        # dedupe any replicated errors and sort by length,
        # shortest first
        deduped_v = sorted(set(v),key=len)                
        e.error_dict[k][0] = '. '.join(deduped_v)

    
@toolkit.chained_action
def user_create(original_action, context, data_dict):
    # Force username and email to be lower case
    data_dict["email"] = data_dict.get("email").lower()
    data_dict["name"] = data_dict.get("name").lower()
    result = original_action(context, data_dict)
    return result


@toolkit.chained_action
def user_list(original_action, context, data_dict):
    query = original_action(context | {'return_query': True}, data_dict)

    # Modify CKAN query to return extra information to assist admins in auditing users
    is_org_member = sa.case(
        [(sa.exists().where(sa.and_(
            Member.table_id == sa.cast(User.id, sa.String),
            Member.table_name == 'user',
            Member.state == 'active',            
            Member.group_id.isnot(None)            
        )), True)], else_=False).label('is_organization_member')

    is_collaborator = sa.case(
        [(sa.exists().where(sa.and_(        
            PackageMember.user_id == sa.cast(User.id, sa.String),
            PackageMember.capacity == 'member',
            PackageMember.package_id.isnot(None)
        )), True)], else_=False).label('is_collaborator')

    
    query = query.add_columns(User.sysadmin, User.plugin_extras, is_org_member, is_collaborator)    

    if context.get('return_query'):
        return query
    else:
        # an API request so run query and dictize results
        users_list: ActionResult.UserList = []
        all_fields = asbool(data_dict.get('all_fields', None))
        
        for user in query.all():                
            result_dict = model_dictize.user_dictize(user[0], context)
            result_dict['is_collaborator'] = user.is_collaborator
            result_dict['is_email_verified'] = is_email_verified(user)
            result_dict['is_organization_member'] = user.is_organization_member
            
            users_list.append(result_dict)
        
        return users_list
