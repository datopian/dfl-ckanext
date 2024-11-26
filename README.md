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


## Installation

**TODO:** Add any additional install steps to the list below.
   For example installing any non-Python dependencies or adding any required
   config settings.

To install ckanext-gla:

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/Swirrl/ckanext-gla.git
    cd ckanext-gla
    pip install -e .
	pip install -r requirements.txt

3. Add `gla` to the `ckan.plugins` setting in your CKAN
   config file (by default the config file is located at
   `/etc/ckan/default/ckan.ini`).

4. Restart CKAN. For example if you've deployed CKAN with Apache on Ubuntu:

     sudo service apache2 reload


## Developer installation

To install ckanext-gla for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/Swirrl/ckanext-gla.git
    cd ckanext-gla
    python setup.py develop
    pip install -r dev-requirements.txt


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## Releasing a new version of ckanext-gla

If ckanext-gla should be available on PyPI you can follow these steps to publish a new version:

1. Update the version number in the `setup.py` file. See [PEP 440](http://legacy.python.org/dev/peps/pep-0440/#public-version-identifiers) for how to choose version numbers.

2. Make sure you have the latest version of necessary packages:

    pip install --upgrade setuptools wheel twine

3. Create a source and binary distributions of the new version:

       python setup.py sdist bdist_wheel && twine check dist/*

   Fix any errors you get.

4. Upload the source distribution to PyPI:

       twine upload dist/*

5. Commit any outstanding changes:

       git commit -a
       git push

6. Tag the new release of the project on GitHub with the version number from
   the `setup.py` file. For example if the version number in `setup.py` is
   0.0.1 then do:

       git tag 0.0.1
       git push --tags

## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
