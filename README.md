[![Tests](https://github.com/Swirrl/ckanext-gla/workflows/Tests/badge.svg?branch=main)](https://github.com/Swirrl/ckanext-gla/actions)

# ckanext-gla

CKAN customisations for the Data for London datastore.

## Config settings

This plugin exposes the following configuration options via
environment variables:

- `SECURE_TOKEN_GENERATION_SECURITY_KEY` Secret key used for all cryptographic tokens.
- `EMAIL_VERIFICATION_TOKEN_EXPIRY` Expiry time in seconds for email verification tokens default `86400`
- `MFA_LOGIN_TOKEN_EXPIRY` Expiry time in seconds for MFA login links (default `300` (5 minutes))

through `ckan.ini` and `custom_options.ini` you can customise the following options:

- `ckan.harvesters.table_formats` space separated list of file formats to classify as "Tables" under the "Format" facet.
- `ckan.harvesters.report_formats` space separated list of file formats to classify as "Reports" under the "Format" facet.
- `ckan.harvesters.geospatial_formats` space separated list of file formats to classify as "Geospatial" under the "Format" facet.
- `dfl.trusted-email-access.regexes` space separated list of regular expressions to determine if a verified email address is trusted (and can access private datasets).
- `dfl.trusted-email-access.optout-org-slugs` space separated list of organisation slugs to determine if an organisation opts out of the above trusted email access feature.

## Requirements

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.9 and earlier | not tested    |
| 2.10.1          | yes           |

Suggested values:

* "yes"
* "not tested" - I can't think of a reason why it wouldn't work
* "not yet" - there is an intention to get it working
* "no"


## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
