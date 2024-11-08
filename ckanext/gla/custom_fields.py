import ckan.plugins.toolkit as toolkit
from ckan.lib.navl.dictization_functions import Invalid
import requests
import json
import os


solr_endpoint = os.getenv("CKAN_SOLR_URL")


def float_validator(value):
    """Ensures that the value is a float and rounds to 4dp."""
    try:
        value = float(value)
        return round(value, 4)
    except:
        raise Invalid("Must be a number")


def data_quality_validator(value):
    try:
        value = int(value)
        if 1 <= value <= 5:
            return value
        raise Invalid("Must be between 1 and 5")
    except:
        raise Invalid("Must be integer")

custom_dataset_fields = {
    "archived": [
        toolkit.get_validator("boolean_validator"),
        toolkit.get_converter("convert_to_extras"),
    ],
    "archived_description": [
        toolkit.get_validator("ignore_missing"),
        toolkit.get_converter("convert_to_extras"),
    ],
    "data_quality": [
        toolkit.get_validator("ignore_empty"),
        data_quality_validator,
        toolkit.get_converter("convert_to_extras"),
    ],
    "data_last_modified": [
        # Didn't put this in extras to make it easier to sort over in results etc
        toolkit.get_validator("ignore_missing"),
        toolkit.get_validator("isodate")
    ],
    "dataset_boost": [float_validator, toolkit.get_converter("convert_to_extras")],
    "project_name": [
        toolkit.get_validator("ignore_missing"),
        toolkit.get_converter("convert_to_extras")],
    "project_url": [
        toolkit.get_validator("ignore_missing"),
        toolkit.get_validator("url_validator"),
        toolkit.get_converter("convert_to_extras"),
    ],
    "entry_type": [
        toolkit.get_validator("one_of")(["analysis", "dataset"]),
        toolkit.get_converter("convert_to_extras")],
    "search_description": [
        toolkit.get_validator("ignore_missing"),
        toolkit.get_converter("convert_to_extras")],
}


fields_to_copy = {
    "extras_data_quality": {"type": "int", "name": "copy_data_quality"},
    "extras_dataset_boost": {"type": "double", "name": "copy_dataset_boost"},
    "title": {"type": "text_phrase_query", "name": "title_phrase"},
    "search_description": {"type": "text_phrase_query", "name": "search_description_phrase"},
    "notes": {"type": "text_phrase_query", "name": "notes_phrase"}
}


def field_exists(field_name):
    api_url = f"{solr_endpoint}/schema/fields/{field_name}"
    response = requests.head(api_url)
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        raise Exception("An error occurred while checking the field.")

def field_type_exists(field_type_name):
    api_url = f"{solr_endpoint}/schema/fieldtypes/{field_type_name}"
    response = requests.head(api_url)
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        raise Exception("An error occurred while checking the field.")
    
    
def add_field(field_name, field_type):
    api_url = f"{solr_endpoint}/schema/fields"
    field_config = {
        "add-field": {
            "name": field_name,
            "type": field_type,
            "stored": "true",
            "indexed": "true"
        }
    }
    response = requests.post(api_url, json=field_config)
    response_json = response.json()
    if not response.status_code == 200 and response_json.get("responseHeader", {}).get("status", -1) == 0:
        raise Exception("Failed to add field", {"name": field_name, "error": response_json})

def add_schema(field_config):
    api_url = f"{solr_endpoint}/schema"
    response = requests.post(api_url, json=field_config)
    response_json = response.json()
    if not response.status_code == 200 and response_json.get("responseHeader", {}).get("status", -1) == 0:
        raise Exception("Failed to add field type", {"error": response_json})


def add_copy_field(from_field, to_field):
    copy_field_config = {
        "add-copy-field": {
            "source": from_field,
            "dest": [to_field]
        }
    }
    api_url = f"{solr_endpoint}/schema"
    response = requests.post(api_url, json=copy_field_config)
    response_json = response.json()
    if not response.status_code == 200 and response_json.get("responseHeader", {}).get("status", -1) == 0:
        print("Copy field added successfully!")
        raise Exception("Failed to add copy field", {"config": copy_field_config,
                                                     "error": response_json})

def add_copy_fields():
    for field, new_field_conf in fields_to_copy.items():
        new_field = new_field_conf["name"]
        if not field_exists(new_field):
            add_field(new_field, new_field_conf["type"])
            add_copy_field(field, new_field)

def add_solr_config():
    # NOTE if you change anything in this function you will likely
    # need to rebuild the SOLR index for changes to be applied to the
    # index.
    #
    # This can be done by running:
    #
    # docker exec -it ckan ckan search-index rebuild
    #

    if not field_type_exists('text_phrase_query'):
        # Like the text type but used for matching against phrase
        # query parts so no synonyms, protwords or stemming.
        add_schema({"add-field-type":
                # This call replaces the default solr-ckan text field
                # type with one that includes configuration changes
                # that support query time synonym replacements via a
                # synonyms.txt file that is defined here:
                #
                # https://github.com/GreaterLondonAuthority/Data_for_London/blob/develop/ckan-solr/synonyms.txt
                #
                {
                    "name": "text_phrase_query",
                    "class": "solr.TextField",
                    "positionIncrementGap": 100,
                    "indexAnalyzer": {
                        "tokenizer": {
                            "class": "solr.WhitespaceTokenizerFactory"
                        },
                        "filters": [
                            {
                                "class": "solr.WordDelimiterGraphFilterFactory",
                                "generateWordParts": 1,
                                "generateNumberParts": 1,
                                "catenateWords": 1,
                                "catenateNumbers": 1,
                                "catenateAll": 0,
                                "splitOnCaseChange": 1
                            },
                            {
                                "class": "solr.FlattenGraphFilterFactory"
                            },
                            {
                                "class": "solr.LowerCaseFilterFactory"
                            },
                            {
                                "class": "solr.ASCIIFoldingFilterFactory"
                            }
                        ]
                    },
                    "queryAnalyzer": {
                        "tokenizer": {
                            "class": "solr.WhitespaceTokenizerFactory"
                        },
                        "filters": [
                            {
                                "class": "solr.WordDelimiterGraphFilterFactory",
                                "generateWordParts": 1,
                                "generateNumberParts": 1,
                                "catenateWords": 0,
                                "catenateNumbers": 0,
                                "catenateAll": 0,
                                "splitOnCaseChange": 1
                            },
                            {
                                "class": "solr.LowerCaseFilterFactory"
                            },
                            {
                                "class": "solr.ASCIIFoldingFilterFactory"
                            }
                        ]
                    }
                }
                })

    add_schema({"replace-field-type":
                # This call replaces the default solr-ckan text field
                # type with one that includes configuration changes
                # that support query time synonym replacements via a
                # synonyms.txt file that is defined here:
                #
                # https://github.com/GreaterLondonAuthority/Data_for_London/blob/develop/ckan-solr/synonyms.txt
                # 
                {
                    "name": "text",
                    "class": "solr.TextField",
                    "positionIncrementGap": 100,                    
                    "indexAnalyzer": {
                        "tokenizer": {
                            "class": "solr.WhitespaceTokenizerFactory"
                        },
                        "filters": [
                            {
                                "class": "solr.WordDelimiterGraphFilterFactory",
                                "generateWordParts": 1,
                                "generateNumberParts": 1,
                                "catenateWords": 1,
                                "catenateNumbers": 1,
                                "catenateAll": 0,
                                "splitOnCaseChange": 1
                            },
                            {
                                "class": "solr.FlattenGraphFilterFactory"
                            },
                            {
                                "class": "solr.LowerCaseFilterFactory"
                            },
                            {
                                "class": "solr.SnowballPorterFilterFactory",
                                "language": "English",
                                # NOTE this file is included in the top level Data-for-london repository
                                "protected": "protwords.txt"
                            },
                            {
                                "class": "solr.ASCIIFoldingFilterFactory"
                            }
                        ]
                    },
                    "queryAnalyzer": {
                        "tokenizer": {
                            "class": "solr.WhitespaceTokenizerFactory"
                        },
                        "filters": [
                            {
                                "class": "solr.SynonymGraphFilterFactory",
                                # NOTE this file is included in the top level Data-for-london repository
                                "synonyms": "synonyms.txt",
                                "ignoreCase": True,
                                "expand": True
                            },
                            {
                                "class": "solr.WordDelimiterGraphFilterFactory",
                                "generateWordParts": 1,
                                "generateNumberParts": 1,
                                "catenateWords": 0,
                                "catenateNumbers": 0,
                                "catenateAll": 0,
                                "splitOnCaseChange": 1
                            },
                            {
                                "class": "solr.LowerCaseFilterFactory"
                            },
                            {
                                "class": "solr.SnowballPorterFilterFactory",
                                "language": "English",
                                "protected": "protwords.txt"
                            },
                            {
                                "class": "solr.ASCIIFoldingFilterFactory"
                            }
                        ]
                    }
                }
                })
    
    if not field_exists('dfl_res_format_group'):

        add_schema({"add-field": {"name": "dfl_res_format_group",
                                  "type": "string",
                                  "indexed": True,
                                  "stored": True,
                                  "multiValued": True}})

    if not field_exists('dfl_title_sort'):
        add_schema({
            "add-field-type": {
            "name": "dfl_sortable_text_field",
            "class": "solr.TextField",
            "sortMissingLast": True,
            "multiValued": False,
            "analyzer": {
                "charFilters": [
                    # If we need handle accented characters
                    # differently we may want to uncomment a
                    # configuration like this, and inject the
                    # appropriate character mapping file into the
                    # container. 
                    # 
                    # { "class":
                    # "solr.MappingCharFilterFactory", "mapping":
                    # "mapping-ISOLatin1Accent.txt" },
                    {
                        "class": "solr.PatternReplaceCharFilterFactory",
                        "pattern": "[^a-zA-Z0-9]",
                        "replacement": ""
                    }
                ],
                "tokenizer": {
                    "class": "solr.KeywordTokenizerFactory"
                },
                "filters": [
                    {
                        "class": "solr.LowerCaseFilterFactory"
                    }
                ]
            }
        }})

        add_schema(
            {"add-field": {"name": "dfl_title_sort", "type": "dfl_sortable_text_field"}}
        )
        add_schema({"add-copy-field": {"source": "title", "dest": ["dfl_title_sort"]}})
        add_schema({"add-field": {"name": "frequency", "type": "text"}})
    
    if not field_exists("notes_with_markup"):
        add_schema({"add-field": {"name": "notes_with_markup", "type": "text"}})

    add_copy_fields()
