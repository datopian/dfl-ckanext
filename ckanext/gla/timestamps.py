import json
import dateutil.parser
from datetime import datetime

import ckan.plugins.toolkit as tk


def set_to_now(ctx, _resources):
    updated_timestamp = {"metadata_modified": datetime.now().replace(tzinfo=None)}

    model = ctx["model"]
    # Use SQLAlchemy directly to avoid re-triggering after_package_update:
    (
        model.Session.query(model.Package)
        .filter_by(id=ctx.get("package").id)
        .update(updated_timestamp)
    )


# Priority ordering of possible fields upstream datapress sources use to indicate
# when a dataset was last modified.
RESOURCE_LAST_MODIFIED_FIELDS = ['last_modified', 'check_timestamp', 'upstream_created_at', 'createdAt']

def data_last_modified(package):
    p = tk.get_action("package_show")(None, {"id": package["id"]})

    def resource_date(resource):
        for mod_field in RESOURCE_LAST_MODIFIED_FIELDS:
            if resource.get(mod_field):
                return resource.get(mod_field)

    # For each of the dataset's resources, get the "last_modified" timestamp
    # or the "created" timestamp if that doesn't exist
    resource_modified_dates = [
        d for r in p["resources"] if (d := resource_date(r)) is not None
    ]

    if not resource_modified_dates:
        most_recent_resource_datetime = None
    else:
        # Sort the timestamps in descending order and get the first one
        most_recent = sorted(resource_modified_dates, reverse=True)[0]
        most_recent_resource_datetime = most_recent

    package_extras = {e['key']: e['value'] for e in p.get('extras', [])}

    # Get the most accurate last modified date from the package metadata.
    # This is assuming that the priority order of last modified dates is:
    # 1. `upstream_metadata_modified` (if exists)
    # 2. `data_last_modified` (if exists)
    # 3. `most_recent_resource_datetime` (if exists)
    # 4. `metadata_modified` (this is generated and updated by CKAN; if it doesn't exist, something has gone terribly wrong)
    last_modified = next(
        (
            v
            for v in (
                package_extras.get("upstream_metadata_modified"),
                package.get("data_last_modified"),
                most_recent_resource_datetime,
                package.get("metadata_modified"),
            )
            if v is not None
        ),
        None,
    )

    if not last_modified:
        raise ValueError(
            "No last modified date found in package extras or package data. "
            "Expected at least 'metadata_modified' to be present. "
            "This will break sorting and likely indicates malformed or incomplete package metadata."
        )

    return dateutil.parser.parse(last_modified).replace(tzinfo=None).isoformat()
