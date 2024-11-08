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
RESOURCE_LAST_MODIFIED_FIELDS = ['last_modified', 'check_timestamp', 'created', 'createdAt']
    
def data_last_modified(package):
    p = tk.get_action("package_show")(None, {"id": package["id"]})

    def resource_date(resource):
        for mod_field in RESOURCE_LAST_MODIFIED_FIELDS:
            if resource.get(mod_field):
                return resource.get(mod_field)

            
    # For each of the dataset's resources, get the "last_modified" timestamp
    # or the "created" timestamp if that doesn't exist
    resource_modified_dates = [resource_date(r) for r in p["resources"]]

    # If there were no resources, return None 
    if not resource_modified_dates:        
        return None

    # Sort the timestamps in descending order and get the first one
    most_recent = sorted(resource_modified_dates, reverse=True)[0]
    most_recent_datetime = dateutil.parser.parse(most_recent)
    return most_recent_datetime.replace(tzinfo=None).isoformat()
