from xml.dom.minidom import Identified
from SPARQLWrapper.Wrapper import CSV, TURTLE
from rdflib.term import Identifier
from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, RedirectResponse
from typing import Optional, Any
from pydantic import BaseModel
from enum import Enum
from SPARQLWrapper import SPARQLWrapper, JSON
from SPARQLBurger.SPARQLQueryBuilder import SPARQLGraphPattern, Triple, Filter
from rdflib import Graph
import simplejson as json
from typing import Any, Dict, AnyStr, List, Union, TypeVar
import requests
from fuzzywuzzy import fuzz
import json as stdjson
from rdflib.plugin import register, Parser
import os

# Type definitions for JSON structures
JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]

# Configuring the API router for the license library
router = APIRouter(
    prefix="/licenselibrary",
    tags=["licenselibrary"],
    responses={404: {"description": "Not found"}},
)

# Initialize SPARQLWrapper with the endpoint
sparql = SPARQLWrapper(os.getenv('DB_URL'))

# Enum classes for defining various states in the license library
class ActionState(Enum):
    permitted = 'permitted'
    na = 'na'
    prohibited = 'prohibited'

class DutyState(Enum):
    required = 'required'
    na = 'na'

class TargetState(Enum):
    true = 'yes'
    false = 'no'

# Pydantic models to handle search parameters for licenses
class TargetSearch(BaseModel):
    creativework: TargetState = TargetState.true
    dataset: TargetState = TargetState.true
    software: TargetState = TargetState.true

class ActionsSearch(BaseModel):
    reproduce: ActionState = ActionState.na
    distribute: ActionState = ActionState.na
    modify: ActionState = ActionState.na
    derive: ActionState = ActionState.na
    commercial_use: ActionState = ActionState.na
    charge_distribution_fee: ActionState = ActionState.na
    change_license: ActionState = ActionState.na

class DutiesSearch(BaseModel):
    distribute_duty_attribution: DutyState = DutyState.na
    distribute_duty_notice: DutyState = DutyState.na
    distribute_duty_source_code: DutyState = DutyState.na
    modify_duty_rename: DutyState = DutyState.na
    modify_duty_attribution: DutyState = DutyState.na
    modify_duty_modification_notice: DutyState = DutyState.na
    modify_duty_notice: DutyState = DutyState.na
    modify_duty_source_code: DutyState = DutyState.na
    derive_duty_rename: DutyState = DutyState.na
    derive_duty_attribution: DutyState = DutyState.na
    derive_duty_modification_notice: DutyState = DutyState.na
    derive_duty_notice: DutyState = DutyState.na
    derive_duty_source_code: DutyState = DutyState.na
    change_license_duty_compliant_license = DutyState.na

class LicenseWideDutiesSearch(BaseModel):
    share_alike: DutyState = DutyState.na

class LicenseSearch(BaseModel):
    target: TargetSearch
    actions: ActionsSearch
    duties: DutiesSearch
    license_wide_duties: LicenseWideDutiesSearch

# Enum for different license formats
class LicenseFormat(Enum):
    jsonld = 'json-ld'
    ttl = 'ttl'
    rdfxml = 'rdf-xml'
    #html = 'html'

# Function to flatten JSON-LD IDs
def flatten_ids(obj):
    if isinstance(obj, dict):
        if len(obj) == 1 and '@id' in obj:
            return obj['@id']
        else:
            return {key: flatten_ids(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [flatten_ids(item) for item in obj]
    return obj

# Endpoint to get a license by its ID
@router.get("/license/{license_id}")
def get_license_by_id(license_id, request: Request, format: Optional[LicenseFormat] = LicenseFormat.jsonld, download: Optional[bool] = False):
    """
    Retrieves a specific license by ID in a machine-readable format.

    Parameters:
    * license_id (str): The ID of the license (e.g., "Apache-2.0").
    * format (LicenseFormat, optional): The desired format of the license (json-ld, ttl, rdf-xml).
    * download (bool, optional): If True, provides the license as a downloadable file.
    """
    
    # Redirects to an HTML page if the Accept header is set to text/html
    accept_header = request.headers.get("Accept")
    if "text/html" in accept_header:
        return RedirectResponse(url="https://api.dalicc.net/web/license/" + license_id)

    # Create a graph to parse the license data
    g = Graph()
    try:
        g.parse("licensedata/licenses/" + license_id + ".ttl", format="turtle")
    except Exception:
        pass  # Handle exception if needed

    # Context dictionary for JSON-LD serialization
        context_dict = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "dalicc": "https://dalicc.net/ns#",
        "dalicclib": "https://dalicc.net/licenselibrary/",
        "cc": "http://creativecommons.org/ns#",
        "odrl": "http://www.w3.org/ns/odrl/2/",
        "osl": "http://opensource.org/licenses/",
        "scho": "http://schema.org/"
        }
        
        # Preparing the filename for the output
        filename = "app/temp/" + license_id
        extension = None

        # Serialize the graph to the specified format
        if format == LicenseFormat.jsonld:
            # Register the JSON-LD parser
            register('json-ld', Parser, 'rdflib_jsonld.parser', 'JsonLDParser')
            extension = ".json"
            filename += extension
            license_data = g.serialize(format='json-ld', context=context_dict, indent=2)
            jsonld_dict = stdjson.loads(license_data)
            license_data = flatten_ids(jsonld_dict)
        elif format == LicenseFormat.rdfxml:
            extension = ".xml"
            filename += extension
            license_data = g.serialize(format='xml')
        elif format == LicenseFormat.ttl:
            extension = ".ttl"
            filename += extension
            license_data = g.serialize(format='ttl')

        # Handling download option
        if download:
            with open(filename, "w") as f:
                f.write(license_data)
            return FileResponse(path=filename, filename=license_id + extension)
        else:
            return license_data if format == LicenseFormat.jsonld else license_data

        
# Function to calculate similarity score between strings
def similarity_score(s_input, s_comparison):
    """
    Calculates the similarity score between two strings using fuzzy matching.

    Parameters:
    * s_input (str): Input string.
    * s_comparison (str): String to compare against.
    """
    # Fuzzy matching logic
    return fuzz.ratio(s_input.lower(), s_comparison.lower())


# Endpoint to list licenses in the license library
@router.get("/list")
def list_licenses_in_the_license_library(keyword: Optional[str] = None, skip: Optional[int] = 0, limit: Optional[int] = 10):
    """
    Lists the licenses stored in the license library, optionally filtered by a keyword.

    Parameters:
    * keyword (str, optional): A keyword to filter the licenses by their title.
    * skip (int, optional): Number of entries to skip for pagination purposes.
    * limit (int, optional): Maximum number of entries to return.
    """

    # Initialize the search terms
    search_terms = keyword.split() if keyword else [""]

    # Construct filter conditions for the SPARQL query based on search terms
    if len(search_terms) > 1:
        # If multiple search terms are present, create a filter condition for each
        s1 = search_terms[0]
        remaining_terms = search_terms[1:]
        filter_conditions_list = [
            f"((regex(str(?title), '{s1}', 'i') && regex(str(?title), '{sf}', 'i')) || \
              (regex(str(?title), '{s1}', 'i') && regex(str(?title_alternative), '{sf}', 'i')) || \
              (regex(str(?title_alternative), '{s1}', 'i') && regex(str(?title), '{sf}', 'i')) || \
              (regex(str(?title_alternative), '{s1}', 'i') && regex(str(?title_alternative), '{sf}', 'i')))"
            for sf in remaining_terms
        ]
        filter_conditions = " && ".join(filter_conditions_list)
    else:
        # Single search term condition
        filter_conditions = " || ".join(
            f"(regex(str(?title), '{term}', 'i') || regex(str(?title_alternative), '{term}', 'i'))"
            for term in search_terms
        )

    # Formulate the SPARQL query to fetch license data
    query = f"""
                PREFIX dct: <http://purl.org/dc/terms/> 
                PREFIX odrl: <http://www.w3.org/ns/odrl/2/> 
                PREFIX dcmitype: <http://purl.org/dc/dcmitype/> 
                PREFIX dalicc: <https://dalicc.net/ns#> 
                PREFIX cc: <http://creativecommons.org/ns#> 
                SELECT DISTINCT ?id ?title FROM <https://dalicc.net/licenselibrary/> 
                WHERE {{
                    ?id rdf:type odrl:Set;
                        dct:title ?title .
                    OPTIONAL {{ ?id dct:alternative ?title_alternative }} .
                    FILTER ({filter_conditions})
                }}
             """
    
    # Execute the SPARQL query
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    # Sort results based on the keyword, if provided
    if keyword:
        results['results']['bindings'].sort(key=lambda x: similarity_score(keyword, x['title']['value']), reverse=True)
    
    # Extract titles from the results
    results_titles = [entry['title']['value'] for entry in results['results']['bindings']]

    return results


@router.post("/facetedsearch")
def faceted_search(facets: LicenseSearch, skip: Optional[int] = 0, limit: Optional[str] = 10) -> dict:
    """
    Endpoint for searching licenses based on specified criteria.
    This function processes the search request and returns the matching licenses.

    Request body parameters:
    * target: Filter based on the type of target (e.g., creative work, dataset, software)
    * actions: Specify the action state (not applicable, permitted, or prohibited)
    * duties: Indicate the duty state (not applicable or required)
    * license_wide_duties: Specify if wide duties are required or not

    Query parameters:
    * skip: Number of records to skip for pagination.
    * limit: Maximum number of records to return.

    Returns:
        A dictionary of search results.
    """

    # If the limit is the default value (10), set it to a higher value (1000).
    if limit == 10:
        limit = 1000

    # Mapping of duties to their corresponding URIs.
    duty_map = {
        "attribution": "cc:Attribution",
        "notice": "cc:Notice",
        "source_code": "cc:SourceCode",
        "rename": "dalicc:rename",
        "modification_notice": "dalicc:modificationNotice",
        "compliant_license": "dalicc:compliantLicense",
        "share_alike": "cc:ShareAlike"
    }

    # Mapping of actions to their corresponding URIs.
    action_map = {
        "reproduce": "odrl:reproduce",
        "distribute": "odrl:distribute",
        "modify": "odrl:modify",
        "derive": "odrl:derive",
        "commercial_use": "cc:CommercialUse",
        "charge_distribution_fee": "dalicc:chargeDistributionFee",
        "change_license": "dalicc:ChangeLicense",
        "share_alike": "cc:ShareAlike"
    }

    # Combine action and duty maps into a single map for processing.
    p_map = action_map.copy()
    for kd in duty_map:
        for ka in action_map:
            p_map[ka + "_duty_" + kd] = duty_map[kd]

    # SPARQL prefixes used in constructing the query.
    prefixes = """
    PREFIX dct: <http://purl.org/dc/terms/> 
    PREFIX odrl: <http://www.w3.org/ns/odrl/2/> 
    PREFIX dcmitype: <http://purl.org/dc/dcmitype/> 
    PREFIX dalicc: <https://dalicc.net/ns#> 
    PREFIX cc: <http://creativecommons.org/ns#> 
    """

    # Flag to check if any action has been selected
    no_action_selected = True
    for p, value in facets.actions:
        # Check if any action other than 'not applicable' is selected
        if value != ActionState.na:
            no_action_selected = False

    # Start building the 'in' clause for the SPARQL query
    in_clause = "("

    # Base clause for filtering by provenance
    provenance_clause = "?id dct:type "
    provenance_query_clause = ""
    provenance_not_exist_clause = ""

    # Iterate over different types of targets (CreativeWork, Dataset, Software)
    for c, target in [("dalicc:CreativeWork", facets.target.creativework), ("dcmitype:Dataset", facets.target.dataset), ("dcmitype:Software", facets.target.software)]:
        # If the target type is included, add it to the query clauses
        if target == TargetState.true:
            in_clause += c + ","
            provenance_query_clause += provenance_clause + c + ".\n"
        # If the target type is explicitly excluded, add a 'not exists' clause
        if target == TargetState.false:
            provenance_not_exist_clause += "FILTER NOT EXISTS{\n ?asset dct:type " + c + ".\n}\n"

    # Finalize the in_clause by removing the last comma and closing the parenthesis
    in_clause = in_clause[:-1] + ")"
    in_clause = "FILTER (?assettype IN " + in_clause + ")."

    # If all target types are set to false, clear the in_clause
    if (facets.target.creativework == facets.target.dataset == facets.target.software == TargetState.false):
        in_clause = ""

    # If no specific action is selected, construct a query based on license-wide duties
    if no_action_selected:
        sa_addition = ""
        # If share-alike duty is required, add it to the query
        if facets.license_wide_duties.share_alike == DutyState.required:
            p_cur_id = 1000  # Placeholder ID for permission
            d_cur_id = 1001  # Placeholder ID for duty
            sa_addition += "?id odrl:duty ?d" + str(d_cur_id) + ". \n ?d" + str(d_cur_id) + " odrl:action " + p_map["share_alike"] + ".\n"

        # Construct the final query with all parts
        query = """SELECT DISTINCT ?id ?title FROM <https://dalicc.net/licenselibrary/> 
                WHERE
                { {
                ?id odrl:target ?asset.
                ?id dct:title ?title.
                ?asset dct:type ?assettype.
                """ + sa_addition + """
                }
                """ + in_clause + """
                """ + provenance_not_exist_clause + """
                }"""

        # Set and execute the SPARQL query
        sparql.setQuery(prefixes + query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()

        # Post-process the results to update URLs and sort by title
        for r in results:
            for k in results["results"]["bindings"]:
                k["id"]["value"] = k["id"]["value"].replace("http:", "https:")

        results['results']['bindings'].sort(key=lambda x: x['title']['value'])
        return results

    # Flags to ensure specific parts of the query are only added once
    permission_once = True
    prohibition_once = True

    # Starting the SPARQL query for selecting distinct IDs and titles from a specific source
    query = "SELECT DISTINCT ?id ?title FROM <https://dalicc.net/licenselibrary/> \nWHERE\n{\n{"

    # Preparing unique identifiers for permissions and duties in the SPARQL query
    p_set = set(map(str, range(1, 15)))  # Set of IDs for permissions
    d_set = set(map(str, range(1, 150))) # Set of IDs for duties

    # Adding a base part of the query to select id and title
    query += "?id dct:title ?title.\n"

    # Looping through each action in the facets
    for p, value in facets.actions:
        p_cur_id = p_set.pop()  # Get a unique ID for each permission

        # If the action is allowed (permitted)
        if value == ActionState.permitted:
            # Adding a permission clause to the query
            query += "?id odrl:permission ?p" + str(p_cur_id) + ". \n ?p" + str(p_cur_id) + " odrl:action " + p_map[p] + ".\n"

            # Looping through duties to add required duties to the permission
            for d, value_d in facets.duties:
                d_cur_id = d_set.pop()
                if p in d and value_d == DutyState.required:
                    query += "?p" + str(p_cur_id) + " odrl:duty ?d" + str(d_cur_id) + ". \n ?d" + str(d_cur_id) + " odrl:action " + p_map[d] + ".\n"

            # Ensuring the target and asset type are only added once
            if permission_once:
                query += "?id odrl:target ?asset.\n ?asset dct:type ?assettype."
                permission_once = False

        # If the action is prohibited
        elif value == ActionState.prohibited:
            # Adding a prohibition clause to the query
            query += "?id odrl:prohibition ?p" + str(p_cur_id) + ". \n ?p" + str(p_cur_id) + " odrl:action " + p_map[p] + ".\n"

            # Ensuring the target and asset type are only added once for prohibitions
            if prohibition_once:
                query += "?id odrl:target ?asset.\n ?asset dct:type ?assettype."
                prohibition_once = False

    # If license-wide duty 'share alike' is required, add it to the query
    if facets.license_wide_duties.share_alike == DutyState.required:
        d_cur_id = d_set.pop()
        query += "?id odrl:duty ?d" + str(d_cur_id) + ". \n ?d" + str(d_cur_id) + " odrl:action " + p_map["share_alike"] + ".\n"

    # Finalizing the query with clauses defined earlier
    query += "}" + in_clause + "\n" + provenance_not_exist_clause
    query += "}"

    # Executing the SPARQL query
    sparql.setQuery(prefixes + query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    # Post-processing the results to update http to https and sorting by title
    for r in results:
        for k in results["results"]["bindings"]:
            k["id"]["value"] = k["id"]["value"].replace("http:", "https:")
    results['results']['bindings'].sort(key=lambda x: x['title']['value'])

    return results


@router.post("/composer")
def composer(input_license: Any = Body(..., media_type="text/turtle")) -> dict:
    return


def isAValidJSON(input_json):
    """
    Checks if the input JSON contains the required 'userID' key.

    Args:
        input_json (dict): The JSON object to validate.

    Returns:
        tuple: A tuple containing a boolean and a string. 
               The boolean is True if the 'userID' key exists, 
               otherwise False. The string contains an error 
               message if the key is missing, otherwise None.
    """
    try:
        # Attempt to access the 'userID' key in the input JSON
        input_json[b'userID']
    except KeyError:
        # If a KeyError is raised, it means 'userID' is not present
        return False, "Error: User ID is missing"
    
    # If no exception was raised, the 'userID' key exists
    return True, None
