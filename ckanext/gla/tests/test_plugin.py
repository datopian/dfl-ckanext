"""Tests for plugin.py.

Tests are written using the pytest library (https://docs.pytest.org), and you
should read the testing guidelines in the CKAN docs:
https://docs.ckan.org/en/2.9/contributing/testing.html

To write tests for your extension you should install the pytest-ckan package:

    pip install pytest-ckan

This will allow you to use CKAN specific fixtures on your tests.

For instance, if your test involves database access you can use `clean_db` to
reset the database:

    import pytest

    from ckan.tests import factories

    @pytest.mark.usefixtures("clean_db")
    def test_some_action():

        dataset = factories.Dataset()

        # ...

For functional tests that involve requests to the application, you can use the
`app` fixture:

    from ckan.plugins import toolkit

    def test_some_endpoint(app):

        url = toolkit.url_for('myblueprint.some_endpoint')

        response = app.get(url)

        assert response.status_code == 200


To temporary patch the CKAN configuration for the duration of a test you can use:

    import pytest

    @pytest.mark.ckan_config("ckanext.myext.some_key", "some_value")
    def test_some_action():
        pass
"""
import ckanext.gla.plugin as plugin
import pytest
import ckan.plugins as p

@pytest.mark.ckan_config("ckan.plugins", "gla")
@pytest.mark.usefixtures("with_plugins")
def test_plugin():
    assert p.plugin_loaded("gla")

import ckanext.gla.helpers as h

# dataset page sanitisation wrapper that simulates the pkg_dict info
# we expect.
def dsp_sanitise(html_str):
    pkg_dict = {'name':'my-dataset','upstream_url':'http://upstream/url'}
    return h.sanitise_markup_for_dataset_page(html_str, pkg_dict)

def test_dataset_page_html_sanitisation():
    # TODO
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h1>heading</h1></body></html>')    
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h1>heading</h1></body></html>')
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h3>heading</h3></body></html>')
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h4>heading</h4></body></html>')
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h5>heading</h5></body></html>')
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h6>heading</h6></body></html>')
    assert '<h3>heading</h3>' == dsp_sanitise('<html><body><h7>heading</h7></body></html>')
    # no such thing as h8
    assert '<p>heading</p>' == dsp_sanitise('<html><body><h8>heading</h8></body></html>')

    assert '<h3>heading text</h3>' == dsp_sanitise('<html><body><h2><strong>heading text</strong></h2></body></html>')


    assert '<p>blah blah blah</p><p class="dfl_replaced_image">[an embedded image cannot be displayed here - <a href="http://upstream/url">view on source site</a>]</p>' == dsp_sanitise('<p>blah blah blah</p><img src="data:encoded_img_contents"/>')    
    
    # assert '<html><body><h2>heading</h2></body></html>' == \
    # h.sanitise_markup('<html><body><h2>heading</h2></body></html>', remove_tags=False)

    # assert 'heading other text here' == h.sanitise_markup('<html><body><h2>heading</h2><p>other text here</p></body></html>',
    #                                                       {'name':'my-dataset','upstream_url':'http://upstream/url'})

    # assert 'heading' == h.sanitise_markup('<p>Leave this paragraph intact!</p><p>And this one too!</p>',
    #                                {'name':'my-dataset','upstream_url':'http://upstream/url'})
