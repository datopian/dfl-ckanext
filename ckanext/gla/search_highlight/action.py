import json
import logging
from typing import Any, cast

import ckan
import ckan.authz as authz
import ckan.lib.plugins as lib_plugins
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from ckan.model.user import AnonymousUser
from ckan.common import asbool, config, request, current_user
from ckan.lib import search
from ckan.logic.action.get import ValidationError, _check_access, _validate
from ckan.types import ActionResult, Context, DataDict
from collections import OrderedDict

from flask import has_request_context

log = logging.getLogger(__name__)

GLA_DATASET_FACETS = OrderedDict(
            [
                ("dfl_res_format_group", toolkit._("Format")),
                ("res_format", toolkit._("File type")),
                ("organization", toolkit._("Organisation")),
                #("organization", facets_dict["organization"]),                
                ("project_name", toolkit._("Projects")),
                # Entry type is disabled for now as the value is null for harvested datasets
                # The filter works, so enabling it will allow us to filter for datasets with
                # the field set, either by manual edit, script, or updates to harvester
                # ("entry_type", toolkit._("Type")),
                ("london_smallest_geography", toolkit._("Smallest geography")),
                ("update_frequency", toolkit._("Update frequency"))
            ]
        )

GLA_SYSADMIN_FACETS = GLA_DATASET_FACETS.copy()
GLA_SYSADMIN_FACETS.update({'private': toolkit._("Dataset Visibility")})

def dataset_facets_for_user():
    # Note this function assumes we have checked has_request_context
    # before triggering it.
    if not isinstance(current_user, AnonymousUser) and current_user.sysadmin:
        return GLA_SYSADMIN_FACETS
    else:
        return GLA_DATASET_FACETS

def selected_facets():
    facets_selected = {}
    if has_request_context():
       for (facet_id) in dataset_facets_for_user():
           if facet_id in request.args:
               facets_selected[facet_id] = request.args.getlist(facet_id)
    return facets_selected

# Filter facets so values are only provided for those that have
# either counts > 0 or are selected on the users requested.
def filtered_facets(all_facets):
    # first filter out all zero count facets
    non_zero_or_selected_facets = {k: {ik: iv for ik, iv in v.items() if iv > 0} for k, v in all_facets.items() if isinstance(v, dict)}
    # insert into non_zero facets any selected facets (including ones with count 0)
    for (selected_facet, vals) in selected_facets().items():
        for v in vals:
            if v not in non_zero_or_selected_facets.get(selected_facet,[]):
                non_zero_or_selected_facets[selected_facet] = {v:0}
                #non_zero_or_selected_facets[facet][v] = 0
                    
    return non_zero_or_selected_facets


@toolkit.side_effect_free
def package_search(context: Context, data_dict: DataDict) -> ActionResult.PackageSearch:
    """
    This is a copy of the original package_search function from ckan.logic.action.get
    with the following changes:
    - Add highlighting to return value

    Please update with upstream method when upgrading CKAN.
    TODO: Submit a PR to upstream CKAN to allow for this to be done in a cleaner way.
    """
    # sometimes context['schema'] is None
    schema = context.get("schema") or ckan.logic.schema.default_package_search_schema()
    data_dict, errors = _validate(data_dict, schema, context)

    # put the extras back into the data_dict so that the search can
    # report needless parameters
    data_dict.update(data_dict.get("__extras", {}))
    data_dict.pop("__extras", None)
    if errors:
        raise ValidationError(errors)

    model = context["model"]
    session = context["session"]
    user = context.get("user")

    _check_access("package_search", context, data_dict)

    # Move ext_ params to extras and remove them from the root of the search
    # params, so they don't cause and error
    data_dict["extras"] = data_dict.get("extras", {})
    for key in [key for key in data_dict.keys() if key.startswith("ext_")]:
        data_dict["extras"][key] = data_dict.pop(key)

    # set default search field
    data_dict["df"] = "text"

    # check if some extension needs to modify the search params
    for item in plugins.PluginImplementations(plugins.IPackageController):
        data_dict = item.before_dataset_search(data_dict)

    # the extension may have decided that it is not necessary to perform
    # the query
    abort = data_dict.get("abort_search", False)

    if data_dict.get("sort") in (None, "rank"):
        data_dict["sort"] = config.get("ckan.search.default_package_sort")

    results: list[dict[str, Any]] = []
    facets: dict[str, Any] = {}
    count = 0
    highlighting: dict[str, Any] = {}

    if not abort:
        if asbool(data_dict.get("use_default_schema")):
            data_source = "data_dict"
        else:
            data_source = "validated_data_dict"
        data_dict.pop("use_default_schema", None)

        result_fl = data_dict.get("fl")
        if not result_fl:
            data_dict["fl"] = "id index_id {0}".format(data_source)
        else:
            data_dict["fl"] = " ".join(result_fl)

        data_dict.setdefault("fq", "")

        # Remove before these hit solr FIXME: whitelist instead
        include_private = asbool(data_dict.pop("include_private", False))
        include_drafts = asbool(data_dict.pop("include_drafts", False))
        include_deleted = asbool(data_dict.pop("include_deleted", False))

        if not include_private:
            data_dict["fq"] = "+capacity:public " + data_dict["fq"]

        if "+state" not in data_dict["fq"]:
            states = ["active"]
            if include_drafts:
                states.append("draft")
            if include_deleted:
                states.append("deleted")
            data_dict["fq"] += " +state:({})".format(" OR ".join(states))

        # Pop these ones as Solr does not need them
        extras = data_dict.pop("extras", None)

        # enforce permission filter based on user
        if context.get("ignore_auth") or (user and authz.is_sysadmin(user)):
            labels = None
        else:
            labels = lib_plugins.get_permission_labels().get_user_dataset_labels(
                context["auth_user_obj"]
            )

        query = search.query_for(model.Package)
        query.run(data_dict, permission_labels=labels)

        # Add them back so extensions can use them on after_search
        data_dict["extras"] = extras

        if result_fl:
            for package in query.results:
                if isinstance(package, str):
                    package = {result_fl[0]: package}
                extras = cast("dict[str, Any]", package.pop("extras", {}))
                package.update(extras)
                results.append(package)
        else:
            for package in query.results:
                # get the package object
                package_dict = package.get(data_source)
                ## use data in search index if there
                if package_dict:
                    # the package_dict still needs translating when being viewed
                    package_dict = json.loads(package_dict)

                    if package.get("index_id", False):
                        package_dict["index_id"] = package["index_id"]

                    if context.get("for_view"):
                        for item in plugins.PluginImplementations(
                            plugins.IPackageController
                        ):
                            package_dict = item.before_dataset_view(package_dict)
                    results.append(package_dict)
                else:
                    log.error(
                        "No package_dict is coming from solr for package " "id %s",
                        package["id"],
                    )

        count = query.count
        facets = query.facets
        highlighting = query.highlighting

    search_results: dict[str, Any] = {
        "count": count,
        "facets": facets,
        "results": results,
        "sort": data_dict["sort"],
        "highlighting": highlighting,
    }

    facets = filtered_facets(search_results['facets'])
    search_results['facets'] = facets
    
    # create a lookup table of group name to title for all the groups and
    # organizations in the current search's facets.
    group_names = []
    for field_name in ("groups", "organization"):
        group_names.extend(facets.get(field_name, {}).keys())

    groups = (
        session.query(model.Group.name, model.Group.title)
        # type_ignore_reason: incomplete SQLAlchemy types
        .filter(model.Group.name.in_(group_names)).all()  # type: ignore
        if group_names
        else []
    )
    group_titles_by_name = dict(groups)

    # Transform facets into a more useful data structure.
    restructured_facets: dict[str, Any] = {}
    for key, value in facets.items():
        restructured_facets[key] = {"title": key, "items": []}
        for key_, value_ in value.items():
            new_facet_dict = {}
            new_facet_dict["name"] = key_
            if key in ("groups", "organization"):
                display_name = group_titles_by_name.get(key_, key_)
                display_name = (
                    display_name if display_name and display_name.strip() else key_
                )
                new_facet_dict["display_name"] = display_name
            elif key == "license_id":
                license = model.Package.get_license_register().get(key_)
                if license:
                    new_facet_dict["display_name"] = license.title
                else:
                    new_facet_dict["display_name"] = key_
            else:
                new_facet_dict["display_name"] = key_
            new_facet_dict["count"] = value_
            restructured_facets[key]["items"].append(new_facet_dict)
    search_results["search_facets"] = restructured_facets

    # check if some extension needs to modify the search results
    for item in plugins.PluginImplementations(plugins.IPackageController):
        search_results = item.after_dataset_search(search_results, data_dict)

    # After extensions have had a chance to modify the facets, sort them by
    # display name.
    for facet in search_results["search_facets"]:
        search_results["search_facets"][facet]["items"] = sorted(
            search_results["search_facets"][facet]["items"],
            key=lambda facet: facet["display_name"],
            reverse=True,
        )

    return search_results
