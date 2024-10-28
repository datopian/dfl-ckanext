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

    # NOTE we attempt to implement the main ideas in this spec:
    #
    # https://london.atlassian.net/wiki/spaces/DAT/pages/4292673544/Ingestion+Rendering
    #
    # Though there are also additional measures we implement, e.g.
    # allowing headings but normalising them all to h3.
    
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

    # Test replacing inlined data urls
    assert '<p>blah blah blah</p><p class="dfl_replaced_content">An image has been removed from this description (<a href="http://upstream/url">view upstream</a>)</p>' == dsp_sanitise('<p>blah blah blah</p><img src="data:encoded_img_contents"/>')

    assert '<p>Style tags should be replaced wherever they are</p>' == dsp_sanitise('<p style="color: blue;">Style tags should be replaced wherever they are</p>')
    assert '<p>Style tags should be replaced <em>wherever</em> they are</p>' == dsp_sanitise('<p>Style tags should be replaced <em style="color: red;">wherever</em> they are</p>')

    # Test replacing iframes with links
    assert '<p>blah blah blah: <p class="dfl_replaced_content">Embedded content has been removed from this description (<a href="http://example.org/">view here</a>)</p></p>' == dsp_sanitise('<p>blah blah blah: <iframe src="http://example.org/"/></p>')


    assert '<p class="dfl_replaced_content">An image 〝<em class="replaced_image_description">Example Image</em>〞 has been removed from this description (<a href="http://upstream/url">view upstream</a>)</p>' == dsp_sanitise('<img alt="Example Image" src="http://example.org/external-img.png"/>')

    # handle special case of images surrounded by parent anchor tags
    assert '<p class="dfl_replaced_content">An image 〝<em class="replaced_image_description">Example Image</em>〞 has been removed from this description (<a href="http://upstream/url">view upstream</a>)</p>' == dsp_sanitise('<a href="http://parent.link/"><img alt="Example Image" src="http://example.org/external-img.png"/></a>')

    assert '<ul><li>one</li><li>two</li></ul>' == dsp_sanitise('<ul><li>one</li><li>two</li></ul>')
    assert '<ol><li>one</li><li>two</li></ol>' == dsp_sanitise('<ol><li>one</li><li>two</li></ol>')
    assert '<strong>strong text</strong>' == dsp_sanitise('<strong>strong text</strong>')

    assert '<table><tbody><tr><th>Header</th><th>Header 2</th></tr><tr><td>Cell 1</td><td>Cell 2</td></tr></tbody></table>' == dsp_sanitise('<table><tr><th>Header</th><th>Header 2</th></tr><tr><td>Cell 1</td><td>Cell 2</td></tr></table>')
    assert '<table><caption>Table Caption</caption><tbody><tr><td>Cell</td></tr></tbody></table>' == dsp_sanitise('<table><caption>Table Caption</caption><tr><td>Cell</td></tr></table>')

    assert '<table><thead><tr><th>Header</th></tr></thead><tbody><tr><td>Body cell</td></tr></tbody><tfoot><tr><td>Footer cell</td></tr></tfoot></table>' == dsp_sanitise('<table><thead><tr><th>Header</th></tr></thead><tbody><tr><td>Body cell</td></tr></tbody><tfoot><tr><td>Footer cell</td></tr></tfoot></table>')


