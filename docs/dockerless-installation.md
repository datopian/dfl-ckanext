# Dockerless Installation

If you're working on the Data_for_london project, then you should
follow the instructions in the top level `Data_for_london` application
repository.

If you want to install this extension into a new CKAN environment
outside of the above project, or wish to use it natively on your
localhost the instructions below may be useful:

## Dockerless Installation

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


## Dockerless Developer installation

To install ckanext-gla for development, activate your CKAN virtualenv and
do:

    git clone https://github.com/Swirrl/ckanext-gla.git
    cd ckanext-gla
    python setup.py develop
    pip install -r dev-requirements.txt


## Dockerless Tests

To run the tests, do:

    pytest --ckan-ini=test.ini
