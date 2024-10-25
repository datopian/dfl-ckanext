import os
import re
from typing import Any

import bleach
from bs4 import BeautifulSoup
from markupsafe import Markup

from typing import (
    Any, Callable, Match, NoReturn, cast, Dict,
    Iterable, Optional, TypeVar, Union)

import ckan.logic as logic

import ckan.lib.formatters as formatters
import ckan.plugins.toolkit as toolkit
from ckan.common import _, config, current_user
from ckan.model.user import AnonymousUser
from ckan.lib.helpers import get_translated
from ckan.lib.helpers import render_markdown as original_render_markdown

site_title = config.get("ckan.site_title", "Default Site Title")


def __page_context(request):
    page_info = {"source": "", "is_search": False}
    if request.view_args.get("is_organization"):
        page_info["source"] = "organization"
    else:
        page_info["source"] = "datasets"
    page_info["is_search"] = request.args.get("q") is not None
    return page_info


def __maybe_filter_by_organization(request, datasets):
    if __page_context(request)["source"] == "organization":
        org = request.view_args.get("id")
        return [x for x in datasets if x["dict"]["organization"]["name"] == org]
    else:
        return datasets


def humanise_file_size(file_size):
    size_string = formatters.localised_filesize(file_size)
    humanised_str = size_string.replace("i", "").replace("B", "b").title()
    return humanised_str


def followed(user, request):
    """Get a list of the users followed datasets"""
    if user == "":
        return []
    else:
        followed = toolkit.get_action("followee_list")(None, {"id": user.id})
        followed_datasets = [x for x in followed if x["type"] == "dataset"]
        return __maybe_filter_by_organization(request, followed_datasets)


def should_show_favourites(user, request):
    """Check the dataset page query params to see if we need to show
    the favourite datasets: they're only shown on the first page of items,
    if there is no search term"""
    if user == "" or __page_context(request)["is_search"]:
        return False
    else:
        page = request.args.get("page")
        return page is None or page == "1"


def remove_favourites(user, request, all_items):
    """Filter the list of datasets to exclude favourites shown
    on the top of the page if present"""
    if should_show_favourites(user, request):
        am_following_ds = toolkit.get_action("am_following_dataset")
        return [i for i in all_items if not am_following_ds(None, i)]
    else:
        return all_items


def last_updated(package):
    return package.get("metadata_modified", "")


def extract_resource_format(resource):
    """Extract the format of the resource, used to find the correct icon.
    This was added because .xls files have type 'spreadsheet' and so
    were not being correctly matched to the image associated with type 'xls'.

    The way it works (because it's not obvious) is that this CSS for xls class:
    https://github.com/ckan/ckan/blob/fd88d1f4c52c8ee247883549ca23500693e2e2a4/ckan/public/base/css/main.css#L14033
    is used to set the position of this image containing all the icons so the
    correct one shows:
    https://github.com/ckan/ckan/blob/fd88d1f4c52c8ee247883549ca23500693e2e2a4/ckan/public/base/images/sprite-resource-icons.png
    """

    resource_type = resource.get("format", "data").lower()
    if resource_type == "spreadsheet":
        return "xls"
    elif resource_type == "image":
        return "png"
    else:
        return resource_type


def get_site_title(request):
    """Check if we're on a search or dataset page and, if so, return a title that omits the
    word 'dataset'. Otherwise, return None: the template will show the default title"""

    path_parts = [x for x in request.path.split("/") if x != ""]
    if len(path_parts) == 0:  # we're on the homepage
        return None
    if path_parts == ["dataset"]:  # We're on the dataset search page
        search = request.args.get("q")
        if search is not None and search != "":
            page_title = search
        else:
            page_title = "Search"
        return "{} - {}".format(page_title, site_title)
    elif path_parts[0] == "dataset":  # We're on a dataset or resource page
        context = toolkit.c
        dataset_title = context.get("pkg_dict", {}).get("title")
        return "{} - {}".format(dataset_title, site_title)
    else:
        return None


def sanitise_markup_for_dataset_page(html: str, pkg_dict) -> str:
    """
    Sanitise and fix markup in HTML strings.
    """
    soup = BeautifulSoup(html, "lxml")

    for data in soup(["style", "script", "iframe", "br"]):
        data.decompose()

    return str(soup)

def sanitise_markup_for_search_results(html: str) -> str:
    """
    Sanitise and fix markup in HTML strings for search result context    
    """
    soup = BeautifulSoup(html, "lxml")

    for data in soup(["style", "script", "iframe", "br"]):
        data.decompose()

    # Bleach sanitises HTML string by removing unsafe tags and attributes.
    # It also removes mismatched tags.
    # NOTE: CSS in style arrtibutes isn't sanitised but can be added through additional dependencies,
    # see bleach.CSS_SANITIZER.    
    return bleach.clean(" ".join(soup.stripped_strings), strip=True)

    return str(soup)


def _sanitise_markup(html: str, remove_tags: bool = True) -> str:
    soup = BeautifulSoup(html, "lxml")

    for data in soup(["style", "script", "iframe", "br"]):
        data.decompose()

    if remove_tags:
        return " ".join(soup.stripped_strings)
    # return bleach.clean(str(soup), strip=True)
    return str(soup)


def render_markdown(
    data: str, auto_link: bool = True, allow_html: bool = False
) -> str | Markup:
    """
    Returns the data as rendered markdown

    :param auto_link: Should ckan specific links be created e.g. `group:xxx`
    :type auto_link: bool
    :param allow_html: If True then html entities in the markdown data.
        This is dangerous if users have added malicious content. We remove script and style tags
        ro reduce this risk.
        If False all html tags are removed.
    :type allow_html: bool
    """
    if allow_html:
        data = _sanitise_markup(data.strip(), remove_tags=False)
    return original_render_markdown(data, auto_link, allow_html)


def resource_display_name(resource_dict: dict[str, Any]) -> str:
    name = get_translated(resource_dict, "name")
    description = get_translated(resource_dict, "description")
    if name:
        # Remove file extension from name
        file_path, _junk = os.path.splitext(name)
        file_name_without_extension = os.path.basename(file_path)

        # Remove non-alphanumeric characters from name
        file_name_without_extension = re.sub(
            "[^0-9a-zA-Z ]+", " ", file_name_without_extension
        )

        return file_name_without_extension
    elif description:
        description = description.split(".")[0]
        max_len = 60
        if len(description) > max_len:
            description = description[:max_len] + "..."
        return description
    else:
        return _("Unnamed resource")

def orgs_list_for_user(user: str, permission: str = 'read') -> list[dict[str, Any]]:
    '''Return a list of organizations that the current user has the specified
    permission for.
    '''
    context: Context = {'user': user}
    data_dict = { 'permission': permission}
    orgs = logic.get_action('organization_list_for_user')(context, data_dict)    
    return orgs

def is_sysadmin():
    if not isinstance(current_user, AnonymousUser) and current_user.sysadmin:
        return True
    else:
        return False
    
def get_helpers():
    return {
        "get_followed_datasets": followed,
        "remove_favourites": remove_favourites,
        "show_favourite_datasets": should_show_favourites,
        "last_updated": last_updated,
        "is_search_results_page": lambda request: __page_context(request)["is_search"],
        "extract_resource_format": extract_resource_format,
        "get_site_title": get_site_title,
        "humanise_file_size": humanise_file_size,
        "render_markdown": render_markdown,
        "resource_display_name": resource_display_name,
        "orgs_list_for_user": orgs_list_for_user,
        "is_sysadmin": is_sysadmin
    }
