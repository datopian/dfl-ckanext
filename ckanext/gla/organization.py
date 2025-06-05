import logging
import os
from os.path import exists
from typing import Any, cast
import ckan
import ckan.model as model
from ckan.logic import ActionError
import ckan.plugins.toolkit as tk
import ckan.plugins.toolkit as toolkit
import csv
from ckan import authz
import ckan.lib.base as base
from ckan.common import _

log = logging.getLogger(__name__)

ORGANIZATION_DICT = {}
try:
    with open("organisation_mappings.csv", mode='r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            original_id = row["Original ID"]
            if original_id not in ORGANIZATION_DICT:
                ORGANIZATION_DICT[original_id] = {}
                
            ORGANIZATION_DICT[original_id]['name'] = row["Override ID"]
            ORGANIZATION_DICT[original_id]['title'] = row["Override Title"]
            
except FileNotFoundError as ex:    
    log.info(f"No organisation_mappings.csv file was provided to canonicalise organisation names {ex}")


@toolkit.auth_disallow_anonymous_access
def migrate(context, data_dict={}):     
    requester = context.get("user", None)
    
    if not authz.is_sysadmin(requester):
        return base.abort(403, _("Not authorized to see this page"))

    base_context = {
        "model": model,
        "session": model.Session,
        "user": "ckan_admin",
    }

    organizations = toolkit.get_action("organization_list")(data_dict={})

    for organization in organizations:

        org_mapping = ORGANIZATION_DICT.get(organization,{})

        if org_mapping:

            new_org = None
            try:
                new_org = toolkit.get_action('organization_show')(data_dict={'id': org_mapping['name']})
                # skip over orgs that are already migrated (whos override id exists already)
            except toolkit.ObjectNotFound:
                current_org = toolkit.get_action('organization_show')(data_dict={'id': organization, "include_users": True, "include_datasets": False})

                # create new organization
                new_org_dict = {
                    'name': org_mapping['name'],
                    'title': org_mapping['title'] or current_org['title'] or org_mapping['name'], 
                    "id": org_mapping['name'],
                    'description': current_org["description"],
                    'image_url' : current_org["image_url"],
                    'is_organization': True,
                    'state': 'active',
                    "extras": current_org.get("extras", [])
                }
                new_org = toolkit.get_action('organization_create')(base_context, new_org_dict)

                # migrate the subgroups
                for subgroup in current_org["groups"]:
                    toolkit.get_action("group_create")(context, {
                        "name": subgroup["name"],
                        "title": subgroup["title"],
                        "description": subgroup.get("description", ""),
                        "state": "active",
                        "organization_id": new_org["id"]
                    })

                 # migrate users and their roles
                for user in current_org["users"]:
                    toolkit.get_action("organization_member_create")(context, {
                        "id": new_org["id"],
                        "username": user["name"],
                        "role": user["capacity"]
                    })

                log.info("Organization %s has been newly created", org_mapping)

            datasets = get_datasets_by_org(organization, base_context)

            for dataset in datasets:
                try:
                    toolkit.get_action('package_owner_org_update')(
                        base_context,
                        {
                            'id': dataset["id"], 
                            'organization_id': new_org["id"]
                        }
                    )
                    log.info(f"dataset updated '{dataset['id']}'")
                except ActionError as e:
                    log.warning(f"FAILED to update dataset for org '{dataset['owner_org']}' for ID '{dataset['id']}'.")

            remaining_datasets = get_datasets_by_org(organization, base_context)
            if not remaining_datasets:
                try:
                    toolkit.get_action('organization_delete')(base_context, {'id': organization})
                    log.info(f"Old organization '{organization}' deleted.")
                except ActionError as ve:
                    log.exception(f"FAILED to delete old organization '{organization}' as it still has datasets.")
                    
            else:
                log.warning(f"Old organization '{organization}' still has datasets and cannot be deleted.")

    return "get_migrate_organizations completed"

def get_datasets_by_org(org_name, context):
    search_result = toolkit.get_action('package_search')(
    context, {
        'fq': f'organization:{org_name}', 
        'rows': 1000,
        'include_private': True,
        'include_drafts': True,
        'include_deleted': True
        }
    )
    return search_result['results']
