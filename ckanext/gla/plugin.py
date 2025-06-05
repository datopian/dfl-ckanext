import datetime
import dateutil 
import json
import logging
import re
from typing import Any, Mapping, Optional, cast

from markupsafe import Markup

import ckan.lib.mailer as Mailer
import ckan.plugins as plugins
from ckan.lib.plugins import DefaultPermissionLabels
import ckan.plugins.toolkit as toolkit
from ckan.common import _, request
from ckan.config.declaration import Declaration, Key
from ckan.lib import signals
from ckan.lib.helpers import dict_list_reduce, markdown_extract, ungettext
from ckan.model import User, AnonymousUser, Group
from ckan.model.meta import Session
from ckan.types import Schema, Validator
from ckan.plugins.toolkit import get_action
from ckan.logic.validators import isodate

from . import auth, custom_fields, helpers, search, timestamps, user, views, organization
from .search_highlight import (  # query is imported for initialisation, though not explicitly used
    action,
    query,
)
from .search_highlight.action import dataset_facets_for_user, GLA_SYSADMIN_FACETS

from flask import has_request_context

TABLE_FORMATS = toolkit.config.get("ckan.harvesters.table_formats","csv xls xlsx xlsm tsv spreadsheet tab google-sheet").split(" ")
REPORT_FORMATS = toolkit.config.get("ckan.harvesters.report_formats","zip html htm pdf docx doc odw").split(" ")
GEOSPATIAL_FORMATS = toolkit.config.get("ckan.harvesters.geospatial_formats","geojson shp mbtiles kml").split(" ")

def load_config_as_list(key):
    val = toolkit.config.get(key,'')
    if val:
        return list(filter(lambda x: x != '', val.split(' ')))
    else:
        return []


TRUSTED_EMAIL_REGEXES = load_config_as_list("dfl.trusted-email-access.regexes")
TRUSTED_EMAIL_ORG_OPT_OUTS = set(load_config_as_list("dfl.trusted-email-access.optout-org-slugs"))

log = logging.getLogger(__name__)

def build_multi_select_facet_constraints() -> dict[str, Any]:
    # fields_grouped will contain a dict of params containing
    # a list of values eg {u'tags':[u'tag1', u'tag2']}

    fields_grouped = {}
    for (facet_id) in dataset_facets_for_user():
        if facet_id in request.args:
            fields_grouped[facet_id] = request.args.getlist(facet_id)

    fq_parts = []

    for key, vals in fields_grouped.items():
        quoted_vals = [f'"{val}"' for val in vals]
        query_part = f"{{!tag={key}}}{key}:({' OR '.join(quoted_vals)})"

        fq_parts.append(query_part)

    return fq_parts

def build_fq_regex(keys):
    # build alternation string for regex e.g. "res_format|organization|dfl_res_format_group"
    keys_to_remove = '|'.join(re.escape(key) for key in keys)
    values = r'(?:[^\s"]+|"[^"]*")' # quoted or unquoted values
    return r'\b(' + keys_to_remove + r'):' + values


# GLA_SYSADMIN_FACETS has the complete set of facets we display on the
# UI, so these are the ones we need to clean up from the fq parameter.
FQ_REMOVE_PATTERN = build_fq_regex(GLA_SYSADMIN_FACETS.keys())

# CKAN builds the fq parameter before passing it to
# before_dataset_search.
#
# However the way it builds the fq parameter assumes AND within a
# facet, and is also used for introducing extra constraints as per the
# view. Hence we need to preserve some of the items from fq, and
# ultimately rebuild it to support multi select.
#
# In this part of the query we remove anything from the supplied fq
# string that is targetting one of our explicit facets (where we want
# multi-select). Anything else in fq is left alone to ensure those
# constraints are kept.
def cleanup_fq(fq):
    result = re.sub(FQ_REMOVE_PATTERN, '', fq)
    result = re.sub(r'\s+', ' ', result).strip()
    return result

# Allow list of routes that support multi-select facets. Routes not
# matched by these expressions will not have their SOLR queries
# altered by the multi-select query logic.
#
# This ensures routes like /api and /harvest and any others we have
# not opted in are not affected by our custom facet logic.
MULTI_SELECT_ROUTES = [
    r'^/dataset\/?$',
    r'^/organization(/[^/]+/?)?$', # matches /organization, /organization/foo and /organization/foo/
                                   # but not /organization/foo/anything-else
    r'^/organization/bulk_process(/[^/]+/?)?$'
]

def is_multi_select_route(request):
    if has_request_context(): # be mindful that some API requests are not over HTTP but via the python action API
       for r in MULTI_SELECT_ROUTES:
           if re.match(r,request.path):
               return True
    return False

def isodate_string(value, context):
    date = isodate(value,context) # this will raise an invalid exception for us
    return value

def patch_missing_organisation(result):
    if not result.get('organization'):
        result['organization'] = {"name":"unknown", "title":"Unknown Organisation"}
    if not result.get('organization').get("title"):
        result['organization']['title'] = "Unknown Organisation"

def update_with_file_size(package_dict):
    if package_dict.get("num_resources", 0) > 0:
        total_file_size = sum(
            item["size"]
            for item in package_dict.get("resources", [])
            if item and item["size"] is not None
        )

        if total_file_size > 0:
            package_dict["total_file_size"] = total_file_size

class GlaPlugin(plugins.SingletonPlugin, toolkit.DefaultDatasetForm, DefaultPermissionLabels):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.IAuthFunctions, inherit=True)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IDatasetForm)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IPermissionLabels)

    def get_validators(self) -> dict[str, Validator]:
        return {
            "isodate_string": isodate_string
        }

    # IConfigDeclaration
    def declare_config_options(self, declaration: Declaration, key: Key):
        declaration.declare_list(key.ckan.harvesters.table_formats, [])
        declaration.declare_list(key.ckan.harvesters.report_formats, [])
        declaration.declare_list(key.ckan.harvesters.geospatial_formats, [])

    # IConfigurer
    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "gla")
        custom_fields.add_solr_config()

    # IAuthFunctions
    def get_auth_functions(self):
        auth_functions = {"user_list": auth.user_list, "user_show": auth.user_show}
        return auth_functions

    # IPackageController
    def before_dataset_search(self, search_params):
        # Include showcases *and* datasets in the search results:
        # We only want Showcases to show up when there is a search query
        search_params = search.add_quality_to_search(search_params)
        
        if is_multi_select_route(request):
            # If we're not an API request or a query running on the
            # harvester extension routes trigger the multi-select
            # faceted search behaviour.
            #
            # As the CKAN API allows API users to set the SOLR fq
            # parameter themselves explicitly, we need to avoid doing
            # this for API requests.
            multi_select_fqs = build_multi_select_facet_constraints()

            fq = search_params.get('fq','')

            cleaned_fq = cleanup_fq(fq)
            search_params['fq'] = ''
            multi_select_fqs = [cleaned_fq] + multi_select_fqs

            search_params['fq_init_list'] = multi_select_fqs

            # NOTE the two search_params set below override settings
            # set earlier by CKAN.
            #
            # fq can be replaced entirely with an empty string as our
            # fq_init_list will later replace it.
            search_params['facet.field'] = [f'{{!ex={item}}}' + item for item in search_params.get('facet.field',[])]

        search_params.update(
            {
                "hl": "on",
                "hl.method": "unified",
                "hl.fragsizeIsMinimum": "false",
                "hl.requireFieldMatch": "true",
                "hl.snippets": "1",
                "hl.fragsize": "200",
                "hl.bs.type": "SENTENCE",
                "hl.fl": "title,title_phrase,notes,notes_phrase,search_description,search_description_phrase",
                "hl.simple.pre": "[[",
                "hl.simple.post": "]]",
                "hl.maxAnalyzedChars": "250000",  # only highlight matches occuring in the first 250k characters of a field we increase this from SOLRs default of 51k because some datasets have long descriptions and highlighting wasn't displaying
                "facet.mincount": 0
            }
        )

        return search_params

    # IPackageController
    def before_dataset_view(self, package_dict):
        gla_information = []

        update_with_file_size(package_dict)
        if package_dict.get("num_resources", 0) > 0:
            num_resources = package_dict.get("num_resources", 0)
            files_suffix = ungettext("file", "files", package_dict["num_resources"])

            formats = dict_list_reduce(package_dict.get("resources", []), "format")
            formats = list(map(str.lower, formats))
            formats.sort()
            formats_string = ", ".join(formats)
            if len(formats) > 0:
                formats_string = f"({formats_string})"
            else:
                formats_string = ""

            resource_summary = f"{num_resources} {files_suffix} {formats_string}"

            gla_information.append(resource_summary)

            if package_dict.get('total_file_size',0) > 0:
                gla_information.append(helpers.humanise_file_size(package_dict['total_file_size']))

        for extra in package_dict.get("extras", []):
            if extra["key"] == "update_frequency":
                package_dict["update_frequency_label"] = extra["value"]
                gla_information.append(f"Expected update {extra['value'].lower()}")
                break

        package_dict["gla_result_summary"] = " • ".join(gla_information)

        def convert_iso_to_ddmmyyyy(date_str):
            try:
                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                return date_obj.strftime('%d/%m/%Y')
            except ValueError:
                return None

        for resource in package_dict.get("resources",[]):
            if resource.get('upstream_created_at'):
                # CKAN views expect this field as a datetime object
                created_at = resource.get('upstream_created_at')
                resource['upstream_created_at'] = dateutil.parser.isoparse(created_at)
            if resource.get('temporal_coverage_from'):
                resource['temporal_coverage_from'] = convert_iso_to_ddmmyyyy(resource.get('temporal_coverage_from'))
            if resource.get('temporal_coverage_to'):
                resource['temporal_coverage_to'] = convert_iso_to_ddmmyyyy(resource.get('temporal_coverage_to'))
        
        return package_dict

    def after_dataset_show(self, context, package_dict):
        update_with_file_size(package_dict)
        return package_dict

    def after_dataset_search(
        self, search_results: dict[str, Any], search_params: dict[str, Any]
    ):
        def _get_highlighted_field(
            field_name_in_highlight_dict: str, index_id: str
        ) -> str | None:
            highlighted_field = search_results["highlighting"][index_id].get(
                field_name_in_highlight_dict, None
            )

            if highlighted_field and isinstance(highlighted_field, list):
                return highlighted_field[0]

            return highlighted_field

        def _get_extras_field(
            field_name_in_extras_dict: str, extras_list: list[dict[str, str]]
        ) -> str:
            for extras_dict in extras_list:
                if extras_dict["key"] == field_name_in_extras_dict:
                    return extras_dict["value"]
            return ""

        for result in search_results["results"]:
            index_id = result.get("index_id", False)
            if index_id and index_id in search_results["highlighting"]:
                highlighted_title = _get_highlighted_field("title", index_id) or _get_highlighted_field("title_phrase", index_id)
                
                highlighted_notes = _get_highlighted_field("notes", index_id) or _get_highlighted_field("notes_phrase", index_id)
                highlighted_search_description = _get_highlighted_field(
                    "search_description", index_id
                ) or _get_highlighted_field(
                    "search_description_phrase", index_id
                )
                highlighted_organization_title = _get_highlighted_field(
                    "organization", index_id
                )

                title = highlighted_title or result["title"]
                notes = highlighted_notes or result.get("notes", "")
                search_description = highlighted_search_description or result.get(
                    "search_description", ""
                )

                patch_missing_organisation(result) ## Workaround for issue https://london.atlassian.net/browse/DAT-859
                
                organization = (
                    highlighted_organization_title or result["organization"]["title"]
                )

                # Fall back to notes if search_description is present but not highlighted
                if search_description and "[[" in search_description:
                    search_description = search_description
                else:
                    search_description = notes

                result["title"] = title.replace(
                    "[[", '<span class="dataset-search-highlight">'
                ).replace("]]", "</span>")

                result["organization"]["title"] = organization.replace(
                    "[[", '<span class="dataset-search-highlight">'
                ).replace("]]", "</span>")

                # Handle unclosed tags that flow into the next search result
                sanitized_search_description = str(
                    markdown_extract(search_description, extract_length=500)
                )
                sanitized_search_description_list = []
                for substring in sanitized_search_description.split("[["):
                    if not substring:
                        continue
                    if "]]" in substring:
                        span_content, rest = substring.split("]]")
                        sanitized_search_description_list.append(
                            Markup(
                                f'<span class="dataset-search-highlight">{span_content}</span>'
                            )
                        )
                        sanitized_search_description_list.append(
                            markdown_extract(rest, extract_length=0)
                        )
                    else:
                        sanitized_search_description_list.append(
                            markdown_extract(substring, extract_length=0)
                        )
                result["search_description"] = " ".join(
                    sanitized_search_description_list
                )

        search_facets = search_results['search_facets']

        if 'private' in search_facets:
            for i in search_facets['private']['items']:
                if i['display_name'] == 'true':
                    i['display_name'] = 'Private'
                else:
                    i['display_name'] = 'Public'

        return search_results

    def after_dataset_create(self, ctx, package):
        pass

    def after_dataset_update(self, ctx, package):
        pass

    def after_resource_delete(self, ctx, resources):
        ## timestamps.set_to_now(ctx, resources)
        pass

    def before_dataset_index(self, pkg_dict: dict[str, Any]) -> dict[str, Any]:
        if pkg_dict['type'] != 'dataset':
            # Harvest sources are also "datasets" so only trigger the
            # below logic for real datasets.
            return pkg_dict
            
        
        pkg_dict["notes_with_markup"] = helpers.sanitise_markup_for_dataset_page(
            pkg_dict["notes"], pkg_dict
        )
        pkg_dict["notes"] = helpers.sanitise_markup_for_search_results(pkg_dict["notes"])

        validated_data_dict = json.loads(pkg_dict.get("validated_data_dict", {}))
        validated_data_dict["notes"] = pkg_dict["notes"]

        data_last_modified = timestamps.data_last_modified(pkg_dict)
        pkg_dict['data_last_modified'] = data_last_modified
        
        validated_data_dict["data_last_modified"] = pkg_dict["data_last_modified"]        
        pkg_dict["validated_data_dict"] = json.dumps(validated_data_dict)

        new_format_list = []
        for file_format in pkg_dict.get("res_format", []):
            if file_format.lower() in TABLE_FORMATS:
                new_format_list.append("Tables")
            elif file_format.lower() in REPORT_FORMATS:
                new_format_list.append("Reports")
            elif file_format.lower() in GEOSPATIAL_FORMATS:
                new_format_list.append("Geospatial")
            else:
                continue  # new_format_list.append("Other")

        pkg_dict["dfl_res_format_group"] = new_format_list

        return pkg_dict

    # ITemplateHelpers
    def get_helpers(self):

        def is_trusted_email(user_obj):
            return any(re.search(pattern, user_obj.email) for pattern in TRUSTED_EMAIL_REGEXES)

        def org_opt_outs():
            return TRUSTED_EMAIL_ORG_OPT_OUTS

        def is_org_opted_out(org):
            return org in TRUSTED_EMAIL_ORG_OPT_OUTS

        h = {'is_trusted_email': is_trusted_email,
             'is_email_verified': auth.is_email_verified,
             'is_org_opted_out': is_org_opted_out,
             'org_opt_outs': org_opt_outs}

        return helpers.get_helpers() | h

    # IBlueprint
    def get_blueprint(self):
        return views.get_blueprints()

    # IActions
    def get_actions(self):
        return {
            "debug_dataset_search": search.debug,
            "log_chosen_search_result": search.log_selected_result,
            "package_search": action.package_search,
            "user_create": user.user_create,
            "user_list": user.user_list,
            "migrate_organization": organization.migrate     
        }


    def _modify_package_schema(self, schema: Schema):
        # Add our custom_resource_text metadata field to the schema
        cast(Schema, schema['resources']).update({
            "upstream_created_at": [
                toolkit.get_validator("ignore_missing"),
                toolkit.get_validator("isodate_string")
            ],
            'temporal_coverage_from' : [ toolkit.get_validator('ignore_missing'),
                                         toolkit.get_validator('isodate_string')],
            'temporal_coverage_to' : [ toolkit.get_validator('ignore_missing'),
                                       toolkit.get_validator('isodate_string')]
        })
        return schema

    # IDatasetForm
    # Follows https://docs.ckan.org/en/2.10/extensions/adding-custom-fields.html
    def create_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).create_package_schema()
        schema.update(custom_fields.custom_dataset_fields)
        schema = self._modify_package_schema(schema)
        return schema

    def update_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).update_package_schema()
        schema.update(custom_fields.custom_dataset_fields)
        schema = self._modify_package_schema(schema)
        return schema

    def show_package_schema(self) -> Schema:
        schema = super(GlaPlugin, self).show_package_schema()
        schema.update(
            {
                field: [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ]
                for field in custom_fields.custom_dataset_fields.keys()
            }
        )
        schema.update(
            {
                "harvest_source_title": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
                "harvest_source_frequency": [
                    toolkit.get_converter("convert_from_extras"),
                    toolkit.get_validator("ignore_missing"),
                ],
                "notes_with_markup": [
                    toolkit.get_validator("ignore_missing"),
                ],
            }
        )

        schema = self._modify_package_schema(schema)
        
        return schema

    def is_fallback(self):
        return True

    def package_types(self) -> list[str]:
        return []

    # IFacets
    def dataset_facets(self, facets_dict, _):
        return dataset_facets_for_user()

    def organization_facets(self, facets_dict, *args):
        return dataset_facets_for_user()

    def group_facets(self, facets_dict, *args):
        return dataset_facets_for_user()

    def get_dataset_labels(self, dataset_obj: Any) -> list[str]:
        u'''

        This method works with the corresponding method
        `get_user_dataset_labels`, it is part of CKANs extension API
        it is hooked into by DFL to provide the
        `dfl_trusted_email_access` label, which allows users with
        eligible email addresses to view all private datasets in the
        system published by organisations who have not opted out.

        Organisations who have opted out, as identified by their
        organisation slug, should be space separated in the ckan
        config value `dfl.trusted-email-access.optout-org-slugs`.
        Datasets published by organisations with these identifiers
        will not be tagged with the `dfl_trusted_email_access` tag.

        This method is called during indexing of a dataset, to
        return a list of permission_labels to be associated
        with the supplied dataset.  These labels are then stored
        in the search index and form part of CKANs SOLR queries to ensure
        only datasets that a user has permission to access are returned.

        The algorithm is simple; datasets have many permission_labels
        and users have many permission_labels, and if there is a non
        empty set intersection between a datasets labels and a users
        labels then the user has permission to view that dataset.

        '''

        default_labels = super(GlaPlugin, self).get_dataset_labels(dataset_obj)

        if not dataset_obj.private:
            return default_labels
        else:
            dataset_org_name = Session.query(Group).filter(Group.id==dataset_obj.owner_org).first().name
            if dataset_org_name in TRUSTED_EMAIL_ORG_OPT_OUTS:
                return default_labels
            else:
                return default_labels + [u'dfl_trusted_email_access']


    def get_user_dataset_labels(self, user_obj: Any) -> list[str]:
        u'''
        This method works with the corresponding `get_dataset_labels`
        method, and forms part of CKANs extension API.

        This method may be called before datasets are loaded from the
        SOLR index or before candidate datasets are shown to a user.

        The set of labels returned are compared against a
        corresponding set of labels on a dataset and if they return a
        non empty intersection then the dataset can be viewed by the
        given user.

        We hook into this method to dynamically determine whether a
        users verified email address matches one of the regexes in
        `dfl.trusted-email-access.regexes` if so they are given the
        `dfl_trusted_email_access` label which means they can view
        private datasets from any organisation that has not opted out
        of this feature.

        Opt outs are handled in the corresponding `get_dataset_labels`
        method.
        '''
        labels = super(GlaPlugin, self).get_user_dataset_labels(user_obj)

        if user_obj and not isinstance(user_obj, AnonymousUser):
            has_matching_email = any(re.search(pattern, user_obj.email) for pattern in TRUSTED_EMAIL_REGEXES)

            if(has_matching_email and auth.is_email_verified(user_obj)):
                labels.append(u'dfl_trusted_email_access')

        return labels
