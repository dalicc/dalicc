from app.routers.licenselibrary import LicenseWideDutiesSearch, DutiesSearch, LicenseSearch, TargetState, ActionsSearch, ActionState, DutyState, TargetSearch, faceted_search, list_licenses_in_the_license_library
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from rdflib.namespace import RDF
from typing import Optional, Literal
from rdflib import Graph, Namespace, Literal, BNode, URIRef, XSD
from SPARQLWrapper import SPARQLWrapper, JSON, POST
from rdflib.plugins.serializers.nt import NTSerializer
import requests
import json
import copy
import re
import string
import random
import datetime


# Initialize an API router with a specific prefix and response settings
router = APIRouter(
    prefix="/web",  # Sets the base path for all routes in this router
    tags=["web"],  # Tags for categorizing endpoints
    responses={404: {"description": "Not found"}},  # Default response for a 404 error
)

# Setup a SPARQL wrapper to interact with a SPARQL database endpoint
sparql = SPARQLWrapper("http://virtuoso-db:8890/sparql")

# Jinja2 templates configuration for rendering HTML templates from a specified directory
templates = Jinja2Templates(directory="app/templates")

def generate_random_string(length):
    """
    Generate a random string of a given length.
    The string consists of ASCII letters and digits.
    
    Args:
        length (int): The length of the random string to generate.

    Returns:
        str: A random string.
    """
    characters = string.ascii_letters + string.digits  # Allowed characters
    random_string = ''.join(random.choice(characters) for _ in range(length))  # Generate string
    return random_string

def query_license_data(sparql_endpoint, license_uri):
    """
    Query license data from a SPARQL endpoint using a license URI.

    Args:
        sparql_endpoint (str): The SPARQL endpoint URL.
        license_uri (str): The URI of the license to query.

    Returns:
        list: A list of results from the SPARQL query.
    """
    # Setup SPARQL wrapper for the specified endpoint
    sparql = SPARQLWrapper(sparql_endpoint)
    print("QUERY LICENSE DATA")

    # SPARQL query to retrieve various details about the license
    query = f"""
        PREFIX odrl: <http://www.w3.org/ns/odrl/2/>
        PREFIX cc: <http://creativecommons.org/ns#>
        PREFIX dalicc: <https://dalicc.net/ns#>
        PREFIX dalicclib: <https://dalicc.net/licenselibrary/>
        PREFIX dcmitype: <http://purl.org/dc/dcmitype/>
        PREFIX dct: <http://purl.org/dc/terms/>
        PREFIX osl: <http://opensource.org/licenses/>
        PREFIX spdx: <http://spdx.org/rdf/terms#>
        PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> 

        SELECT ?property ?value ?permission ?prohibition ?duty ?pnduty ?assetType
        WHERE {{
            <{license_uri}> ?property ?value .
            OPTIONAL {{
                ?value rdf:type odrl:Permission.
                ?value odrl:action ?permission .
            }}
            OPTIONAL {{
                ?value rdf:type odrl:Permission.
                ?value odrl:action ?permission .
                ?value odrl:duty ?pduty.
                ?pduty rdf:type odrl:Duty.
                ?pduty odrl:action ?pnduty.
            }}
            OPTIONAL {{
                ?value rdf:type odrl:Prohibition.
                ?value odrl:action ?prohibition .
            }}
            OPTIONAL {{
                ?value rdf:type odrl:Duty.
                ?value odrl:action ?duty .
            }}
            OPTIONAL {{
                ?value rdf:type odrl:AssetCollection.
                ?value dct:type ?assetType .
            }}
        }}
    """
    sparql.setQuery(query)  # Set the query
    print(query)
    sparql.setReturnFormat(JSON)  # Set the return format to JSON

    # Execute the query and return the parsed results
    results = sparql.query().convert()
    return results["results"]["bindings"]


def reconstruct_license_data(license_data):
    """
    Reconstructs the license data into a structured dictionary from the SPARQL query results.

    Args:
        license_data (list): A list of triples, each representing a part of the license data.

    Returns:
        dict: A dictionary representing the structured license data.
    """
    license_dict = {}
    for triple in license_data:
        prop = triple["property"]["value"]

        # Determine the value format based on the data type or language
        if "datatype" in triple["value"]:
            value = triple["value"]["value"]
        elif "xml:lang" in triple["value"]:
            value = {triple["value"]["xml:lang"]: triple["value"]["value"]}
        else:
            value = {"uri": triple["value"]["value"]}

        # Append specific license attributes if they exist
        if "permission" in triple:
            value["permission"] = triple["permission"]["value"]
            if "pnduty" in triple:
                value["pnduty"] = triple["pnduty"]["value"]
        if "prohibition" in triple:
            value["prohibition"] = triple["prohibition"]["value"]
        if "duty" in triple:
            value["duty"] = triple["duty"]["value"]
        if "assetType" in triple:
            value["assetType"] = triple["assetType"]["value"]

        # Aggregate values under the same property
        if prop not in license_dict:
            license_dict[prop] = value
        else:
            if isinstance(license_dict[prop], list):
                license_dict[prop].append(value)
            else:
                license_dict[prop] = [license_dict[prop], value]
    
    return license_dict

def validate(date_text):
    """
    Validates if the provided text is in the correct ISO date format.

    Args:
        date_text (str): Date string to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    try:
        datetime.date.fromisoformat(date_text)
        return True
    except ValueError:
        return False

@router.get("/list", response_class=HTMLResponse)
def html_licenses(request: Request, q: Optional[str] = None, skip: Optional[int] = 0, limit: Optional[str] = 10):
    """
    Returns an HTML response of licenses with optional query, skip, and limit parameters.

    Args:
        request: The HTTP request object.
        q (Optional[str]): Query string for filtering licenses.
        skip (Optional[int]): Number of licenses to skip.
        limit (Optional[str]): Maximum number of licenses to return.

    Returns:
        HTMLResponse: Rendered list of licenses.
    """
    results = list_licenses_in_the_license_library(q, skip, limit)
    return templates.TemplateResponse("list.html", {"request": request, "data": results})

@router.get("/wplist", response_class=HTMLResponse)
def html_licenses(request: Request, q: Optional[str] = None, skip: Optional[int] = 0, limit: Optional[str] = 1000):
    """
    Returns an HTML response of licenses with optional query, skip, and a larger default limit.

    Args:
        request: The HTTP request object.
        q (Optional[str]): Query string for filtering licenses.
        skip (Optional[int]): Number of licenses to skip.
        limit (Optional[str]): Maximum number of licenses to return, default is 1000.

    Returns:
        HTMLResponse: Rendered list of licenses.
    """
    results = list_licenses_in_the_license_library(q, skip, limit)
    return templates.TemplateResponse("wplist.html", {"request": request, "data": results})

@router.get("/compose", response_class=HTMLResponse)
def html_compose(request: Request):
    """
    Returns an HTML response for the license composition interface.

    Args:
        request: The HTTP request object.

    Returns:
        HTMLResponse: Rendered compose interface.
    """
    return templates.TemplateResponse("compose.html", {"request": request})


@router.get("/search", response_class=HTMLResponse)
def html_search(request: Request):
    """
    Returns an HTML response for the general search interface.

    Args:
        request: The HTTP request object.

    Returns:
        HTMLResponse: Rendered search interface.
    """
    return templates.TemplateResponse("search.html", {"request": request})

# /web search for wordpress

@router.get("/wpsearch", response_class=HTMLResponse)
def html_search(request: Request):
    """
    Returns an HTML response for the Wordpress specific search interface.

    Args:
        request: The HTTP request object.

    Returns:
        HTMLResponse: Rendered Wordpress specific search interface.
    """
    return templates.TemplateResponse("wpsearch.html", {"request": request})

@router.get("/wpcomposer", response_class=HTMLResponse)
def html_search(request: Request):
    """
    Returns an HTML response for the Wordpress composer interface.

    Args:
        request: The HTTP request object.

    Returns:
        HTMLResponse: Rendered Wordpress composer interface.
    """
    return templates.TemplateResponse("wpcomposer.html", {"request": request})

@router.post("/wpcomposer")
async def form_post(request: Request):
    """
    Handles the form submission for the Wordpress composer.

    Args:
        request: The HTTP request object containing the form data.

    Returns:
        RedirectResponse: Redirects to the newly created license URL.
    """

    # Initialize an RDF graph
    g = Graph()
    
    # Define a dictionary of namespaces and prefixes for the graph
    prefix_dict = { "bpicountry" : "http://www.bpiresearch.com/BPMO/2004/03/03/cdl/Countries#",
                    "cc" : "http://creativecommons.org/ns#",
                    "dalicc" : "https://dalicc.net/ns#",
                    "dalicclib" : "https://dalicc.net/licenselibrary/",
                    "dcmitype" : "http://purl.org/dc/dcmitype/",
                    "dct" : "http://purl.org/dc/terms/",
                    "foaf" : "http://xmlns.com/foaf/0.1/",
                    "odrl" : "http://www.w3.org/ns/odrl/2/",
                    "osl" : "http://opensource.org/licenses/",
                    "scho" : "http://schema.org/",
                    "spdx" : "http://spdx.org/rdf/terms#",
                    "spdxlicense" : "http://spdx.org/licenses/"}
    
    # Bind the prefixes to the graph and store them in a namespace dictionary
    namespace_dict = {}
    for k in prefix_dict:
        n = Namespace(prefix_dict[k])
        g.bind(k, n)
        namespace_dict[k] = n
        
    # Define a dictionary to map properties to human-readable form
    property_dict = {"https://dalicc.net/ns#additionalClauses" : "Additionalclauses",
                    "http://purl.org/dc/terms/alternative" : "Alternativenames",
                    "http://creativecommons.org/ns#attributionName" : "Attributionname",
                    "http://www.w3.org/ns/odrl/2/duty" : "Duty",
                    "http://purl.org/dc/terms/hasVersion" : "Hasversion",
                    "http://creativecommons.org/ns#jurisdiction" : "Jurisdiction",
                    "http://creativecommons.org/ns#legalcode" : "Legalcode",
                    "https://dalicc.net/ns#LiabilityLimitation" : "Liabilitylimitation",
                    "http://creativecommons.org/ns#license" : "Licensedunder",
                    "http://creativecommons.org/ns#License" : "Licensedunder",
                    "http://www.w3.org/ns/odrl/2/permission" : "Permissions",
                    "http://www.w3.org/ns/odrl/2/prohibition" : "Prohibitions",
                    "https://dalicc.net/ns#PromotionSpecification" : "Promotionspecification",
                    "http://purl.org/dc/terms/publisher" : "Publisher",
                    "http://purl.org/dc/terms/source" : "Source",
                    "http://schema.org/startDate" : "Startdate",
                    "http://www.w3.org/ns/odrl/2/target" : "Target",
                    "http://purl.org/dc/terms/title" : "Title",
                    "http://purl.org/dc/terms/type" : "Type",
                    "http://schema.org/validFor" : "Valid",
                    "https://dalicc.net/ns#validityType" : "Validity",
                    "https//dalicc.net/ns#WarrantyDisclaimer" : "Warrantydisclaimer",
                    "https://dalicc.net/ns#WarrantyOrLiabilityAcceptance" : "Warrantyorliabilityacceptance"}
    
    # Process form data from the request
    form_data = await request.form()
    form_dict = dict(form_data)

    # Generate a unique URI for the new license
    license_uri = generate_random_string(32)
    license_node = URIRef(prefix_dict["dalicclib"] + license_uri)

    # Add basic license information to the graph
    g.add((license_node, RDF.type, namespace_dict["odrl"].Set))
    if "title" in form_dict and form_dict["title"] != "":
        g.add((license_node, namespace_dict["dct"].title, Literal(form_dict["title"])))

    if "creator" in form_dict and form_dict["creator"] != "":
        g.add((license_node, namespace_dict["dct"].publisher, Literal(form_dict["creator"])))
    
    if "validityPeriod" in form_dict and form_dict["validityPeriod"] == "perpetual":
        g.add((license_node, namespace_dict["dalicc"].validityType, namespace_dict["dalicc"].perpetual))
    
    if "validityPeriod" in form_dict and form_dict["validityPeriod"] == "specifyDate":
        g.add((license_node, namespace_dict["dalicc"].validityType, namespace_dict["dalicc"].specifyDate))
        if "startDate" in form_dict and "startDateCheckbox" in form_dict and form_dict["startDateCheckbox"] == "on" and validate(form_dict["startDate"]):
            g.add((license_node, namespace_dict["scho"].startDate, Literal(form_dict["startDate"],datatype=XSD.date)))
        if "endDate" in form_dict and "endDateCheckbox" in form_dict and form_dict["endDateCheckbox"] == "on" and validate(form_dict["endDate"]):
            g.add((license_node, namespace_dict["scho"].endDate, Literal(form_dict["endDate"],datatype=XSD.date)))
    
    if "region" in form_dict and form_dict["region"] == "worldwide":
        g.add((license_node, namespace_dict["cc"].jurisdiction, namespace_dict["dalicc"].worldwide))
    
    if "region" in form_dict and form_dict["region"] == "specifyRegion" and form_dict["country"] != "":
        g.add((license_node, namespace_dict["cc"].jurisdiction, URIRef(prefix_dict["bpicountry"]+form_dict["country"])))
    
    current_permission = None
    
    for k in form_dict:
        if "permission_" in k:
            bn_permission = BNode()
            g.add((license_node, namespace_dict["odrl"].permission, bn_permission))
            g.add((bn_permission, RDF.type, namespace_dict["odrl"].Permission))
            g.add((bn_permission, namespace_dict["odrl"].action, URIRef(prefix_dict[form_dict[k].split(":")[0]]+form_dict[k].split(":")[1])))
            current_permission = bn_permission
        if "pduty_" in k:
            bn_pduty = BNode()
            g.add((bn_pduty, RDF.type, namespace_dict["odrl"].Duty))
            g.add((bn_pduty, namespace_dict["odrl"].action, URIRef(prefix_dict[form_dict[k].split(":")[0]]+form_dict[k].split(":")[1])))
            g.add((current_permission, namespace_dict["odrl"].duty, bn_pduty))
            continue
        if "prohibition_" in k:
            bn_prohibition = BNode()
            g.add((license_node, namespace_dict["odrl"].prohibition, bn_prohibition))
            g.add((bn_prohibition, RDF.type, namespace_dict["odrl"].Prohibition))
            g.add((bn_prohibition, namespace_dict["odrl"].action, URIRef(prefix_dict[form_dict[k].split(":")[0]]+form_dict[k].split(":")[1])))
        if "duty_" in k:
            bn_duty = BNode()
            g.add((license_node, namespace_dict["odrl"].duty, bn_duty))
            g.add((bn_duty, RDF.type, namespace_dict["odrl"].Duty))
            g.add((bn_duty, namespace_dict["odrl"].action, URIRef(prefix_dict[form_dict[k].split(":")[0]]+form_dict[k].split(":")[1])))
        
    bn_target = BNode()
    
    g.add((license_node, namespace_dict["odrl"].target, bn_target))
    g.add((bn_target, RDF.type, namespace_dict["odrl"].AssetCollection))
    
    if "creativeWork" in form_dict and form_dict["creativeWork"] == "on":
        g.add((bn_target, namespace_dict["dct"].type, namespace_dict["dalicc"].CreativeWork))
    if "dataset" in form_dict and form_dict["dataset"] == "on":
        g.add((bn_target, namespace_dict["dct"].type, namespace_dict["dcmitype"].Dataset))
    if "software" in form_dict and form_dict["software"] == "on":
        g.add((bn_target, namespace_dict["dct"].type, namespace_dict["dcmitype"].Software))
    
    if "licensedUnder" in form_dict and form_dict["licensedUnder"] != "":
        g.add((license_node, namespace_dict["cc"].license, URIRef(form_dict["licensedUnder"])))
        
    # Serialize the graph to Turtle format
    new_license_ttl = g.serialize(format="turtle")

    # Prepare form data for serialization
    fd = form_dict.copy()
    fd.pop("g-recaptcha-response")

    # Serialize the graph to N-Triples format
    serializer = NTSerializer(g)
    nt_string = g.serialize(format='nt')

    # Insert the serialized data into a SPARQL endpoint
    custom_licenses_graph_uri = "https://dalicc.net/customlicenses/"
    sparqlc = SPARQLWrapper("http://virtuoso-db:8890/sparql")
    sparqlc.method = 'POST'
    query = f"""
        INSERT {{
            GRAPH <{custom_licenses_graph_uri}> {{
                {nt_string}
            }}
        }}
    """
    sparqlc.setQuery(query)
    sparqlc.query()

    # Redirect to the newly created license URL
    url = prefix_dict["dalicclib"] + license_uri
    response = RedirectResponse(url=url)
    return response

def avoid_splitting_acronyms(value, acronyms):
    """
    Modifies a string to avoid splitting acronyms during further processing.

    Args:
        value (str): The original string that may contain acronyms.
        acronyms (list): A list of acronyms that should not be split.

    Returns:
        str: The modified string with acronyms preserved.
    """
    
    # Create a dictionary to store placeholders for each acronym
    placeholderDict = dict()
    
    # Iterate over each acronym
    i = 1
    for acronym in acronyms:
        # Create a unique placeholder for the acronym
        placeholderDict[acronym] = 'PLACEHOLDER' + str(i)
        i += 1

        # Temporarily replace the acronym with its placeholder
        value = value.replace(acronym, placeholderDict[acronym])

    # Add spaces before capital letters that are not at the start of a word
    # This helps in processing or formatting, while preserving the acronyms
    value = re.sub(r"(?<=[a-z])([A-Z])", r' \1', value)

    # Replace each placeholder with the original acronym
    for acronym in placeholderDict:
        placeholder = placeholderDict[acronym]
        value = value.replace(placeholder, acronym)

    return value

def transform_license_info(propertyToTextDict, licenseDict, licenseID):
    """
    Transforms license information into a more readable and structured format.

    Args:
        propertyToTextDict: A dictionary mapping RDF properties to human-readable text.
        licenseDict: A dictionary containing the properties and values of a license.
        licenseID: Identifier of the license.

    Returns:
        A dictionary with structured and readable license information.
    """
    
    # Initialize a dictionary to hold the transformed license information
    outputDict = {}
    
    # Iterate over each property in the license dictionary
    for key, value in licenseDict.items():
        # Check if the property is recognized and should be transformed
        if key in propertyToTextDict:
            # Special formatting for date properties
            if key in ["http://schema.org/startDate", "http://schema.org/endDate"]:
                value = {'uri': value}
            # Map the RDF property to a more readable key name
            keyName = propertyToTextDict[key]

            # Special handling for permissions, prohibitions, duties, targets, and alternative names
            if any(term in key for term in ['permission', 'prohibition', 'target', 'alternative', 'duty']):
                # Ensure value is a list for consistent processing
                ivalue = value if isinstance(value, list) else [value]

                # Processing permissions
                if 'permission' in key:
                    actions = []
                    for item in ivalue:
                        actionName = format_action_name(item['permission'])
                        actionDict = {'action': actionName}
                        if 'pnduty' in item:
                            duty = format_action_name(item['pnduty'])
                            actionDict.setdefault('duties', []).append(duty)
                        actions.append(actionDict)
                    outputDict[keyName] = actions

                # Processing prohibitions
                elif 'prohibition' in key:
                    outputDict[keyName] = [format_action_name(item['prohibition']) for item in ivalue]

                # Processing duties
                elif 'duty' in key:
                    outputDict[keyName] = [format_action_name(item['duty']) for item in ivalue]

                # Processing targets
                elif 'target' in key:
                    targets = [format_target_type(item['assetType']) for item in ivalue]
                    outputDict[keyName] = customize_target_output(targets)

                # Processing alternative names
                elif 'alternative' in key:
                    outputDict[keyName] = [item['uri'] for item in ivalue]

                # Sort the list if it contains dictionary elements
                if keyName in outputDict and isinstance(outputDict[keyName], list) and all(isinstance(elem, dict) for elem in outputDict[keyName]):
                    outputDict[keyName] = sorted(outputDict[keyName], key=lambda x: x['action'])
                else:
                    outputDict[keyName].sort()

            # Handling all other property types
            else:
                # Check if the value is a dictionary and process accordingly
                if isinstance(value, dict):
                    vkeys = list(value.keys())
                    if len(vkeys) == 1:
                        ikey = vkeys[0]

                # Handling specific cases like legal code or source
                if 'legalcode' in key or 'source' in key:
                    outputDict[keyName] = [value[ikey]]
                else:
                    # Avoid splitting acronyms and apply formatting
                    avoid = ["ODbL", "LaTeX"]
                    formatted_value = format_and_avoid_acronyms(value[ikey], avoid)
                    outputDict[keyName] = [formatted_value]

    # Special handling for SPDX license ID
    if 'http://spdx.org/rdf/terms#licenseId' in licenseDict:
        outputDict['SPDX'] = licenseDict['http://spdx.org/rdf/terms#licenseId']['uri']

    # Add license ID to the output
    outputDict['id'] = licenseID

    return outputDict


def transform_dict(inputDict):
    """
    Transforms the input dictionary by grouping duties under the same actions 
    and eliminating duplicate entries in permissions and prohibitions.

    Args:
        inputDict (dict): The input dictionary containing license details.

    Returns:
        dict: A transformed dictionary with organized permissions and prohibitions.
    """

    # Create a copy of the input dictionary to avoid modifying the original
    outputDict = inputDict.copy()

    # Initialize a dictionary to group duties by their actions
    actionDict = {}
    
    # Check and process 'Permissions' if they exist in the input dictionary
    if 'Permissions' in outputDict:
        for item in outputDict['Permissions']:
            # Extract the action and duties from each permission item
            action = item['action']
            duties = item.get('duties', [])

            # Remove duplicate duties and sort them
            duties = list(set(duties))
            duties.sort()

            # Group duties by their respective actions
            if action in actionDict:
                actionDict[action].extend(duties)
            else:
                actionDict[action] = duties
    
    # Reconstruct the 'Permissions' section in the output dictionary
    # to have a list of unique actions and their grouped duties
    if 'Permissions' in outputDict:
        outputDict['Permissions'] = [{'action': action, 'duties': list(set(duties))} for action, duties in actionDict.items()]

    # Ensure that 'Prohibitions' are unique in the output dictionary
    if 'Prohibitions' in outputDict:
        outputDict['Prohibitions'] = list(set(outputDict['Prohibitions']))
    
    return outputDict


@router.get("/license/{license_id}", response_class=HTMLResponse)
def html_search(request: Request, license_id):
    """
    Retrieves and displays the license information for a given license ID in HTML format.

    Args:
        request (Request): The HTTP request object.
        license_id (str): The identifier of the license to be retrieved.

    Returns:
        HTMLResponse: Rendered HTML page showing detailed information about the license.
    """

    # Mapping of RDF properties to more human-readable text
    propertyToTextDict = {"https://dalicc.net/ns#additionalClauses" : "Additionalclauses",
                            "http://purl.org/dc/terms/alternative" : "Alternativenames",
                            "http://creativecommons.org/ns#attributionName" : "Attributionname",
                            "http://www.w3.org/ns/odrl/2/duty" : "Duty",
                            "http://purl.org/dc/terms/hasVersion" : "Hasversion",
                            "http://creativecommons.org/ns#jurisdiction" : "Jurisdiction",
                            "http://creativecommons.org/ns#legalcode" : "Legalcode",
                            "https://dalicc.net/ns#LiabilityLimitation" : "Liabilitylimitation",
                            "http://creativecommons.org/ns#license" : "Licensedunder",
                            "http://creativecommons.org/ns#License" : "Licensedunder",
                            "http://www.w3.org/ns/odrl/2/permission" : "Permissions",
                            "http://www.w3.org/ns/odrl/2/prohibition" : "Prohibitions",
                            "https://dalicc.net/ns#PromotionSpecification" : "Promotionspecification",
                            "http://purl.org/dc/terms/publisher" : "Publisher",
                            "http://purl.org/dc/terms/source" : "Source",
                            "http://schema.org/startDate" : "Startdate",
                            "http://www.w3.org/ns/odrl/2/target" : "Target",
                            "http://purl.org/dc/terms/title" : "Title",
                            "http://purl.org/dc/terms/type" : "Type",
                            "http://schema.org/validFor" : "Valid",
                            "https://dalicc.net/ns#validityType" : "Validity",
                            "https//dalicc.net/ns#WarrantyDisclaimer" : "Warrantydisclaimer",
                            "https://dalicc.net/ns#WarrantyOrLiabilityAcceptance" : "Warrantyorliabilityacceptance"}

    # Create an RDF graph
    g = Graph()

    # SPARQL endpoint URL
    endpoint = "http://virtuoso-db:8890/sparql"
    # Constructing the full license URI using the provided license ID
    license_uri = "https://dalicc.net/licenselibrary/" + license_id

    # Querying the license data from the SPARQL endpoint
    license_data = query_license_data(endpoint, license_uri)
    
    # Reconstruct the license data into a more structured format
    license_dict = reconstruct_license_data(license_data)
    
    # Ensure the 'target' field is a list for consistency
    if "http://www.w3.org/ns/odrl/2/target" in license_dict:
        if isinstance(license_dict["http://www.w3.org/ns/odrl/2/target"], dict):
            license_dict["http://www.w3.org/ns/odrl/2/target"] = [license_dict["http://www.w3.org/ns/odrl/2/target"]]

    # Transform the license information for display
    tl_dict = transform_dict(transform_license_info(propertyToTextDict, license_dict, license_id))
    
    # Rendering the license information using a template
    return templates.TemplateResponse("wplicense.html", {"request": request, "data": tl_dict})


@router.post("/searchresults", response_class=HTMLResponse)
async def searchrequest(request: Request, 
                        creativework: TargetState = Form(...), 
                        dataset: TargetState = Form(...), 
                        software: TargetState = Form(...),
                        reproduce: ActionState = Form(...), 
                        distribute: ActionState = Form(...), 
                        modify: ActionState = Form(...), 
                        derive: ActionState = Form(...), 
                        commercial_use: ActionState = Form(...), 
                        charge_distribution_fee: ActionState = Form(...), 
                        change_license: ActionState = Form(...), 
                        share_alike: DutyState = Form(...)):
    """
    Handles the search request and displays the results.

    Args:
        request (Request): The HTTP request object.
        creativework, dataset, software (TargetState): Filters for types of targets (creative work, dataset, software).
        reproduce, distribute, modify, derive, commercial_use, charge_distribution_fee, change_license (ActionState): Filters for actions associated with the license.
        share_alike (DutyState): Filter for the share alike duty.

    Returns:
        HTMLResponse: The rendered HTML template with the search results.
    """

    # Check if at least one type of target is selected, otherwise return to search page
    if not creativework and not dataset and not software:
        # Redirect to the search page if no target is selected
        return templates.TemplateResponse("search.html", {"request": request})

    # Construct the search facets based on the form inputs
    facets = LicenseSearch(
        target=TargetSearch(
            creativework=creativework,
            dataset=dataset,
            software=software
        ),
        actions=ActionsSearch(
            reproduce=reproduce,
            distribute=distribute,
            modify=modify,
            derive=derive,
            commercial_use=commercial_use,
            charge_distribution_fee=charge_distribution_fee,
            change_license=change_license
        ),
        duties=DutiesSearch(
            # Initializing all duty states to 'not applicable' by default
            distribute_duty_attribution=DutyState.na,
            distribute_duty_notice=DutyState.na,
            distribute_duty_source_code=DutyState.na,
            modify_duty_rename=DutyState.na,
            modify_duty_attribution=DutyState.na,
            modify_duty_modification_notice=DutyState.na,
            modify_duty_notice=DutyState.na,
            modify_duty_source_code=DutyState.na,
            derive_duty_rename=DutyState.na,
            derive_duty_attribution=DutyState.na,
            derive_duty_modification_notice=DutyState.na,
            derive_duty_notice=DutyState.na,
            derive_duty_source_code=DutyState.na),
            license_wide_duties=LicenseWideDutiesSearch(share_alike=share_alike)
    )
    
    # Perform the faceted search with the specified filters
    data = faceted_search(facets)

    # Return the search results rendered in the search HTML template
    return templates.TemplateResponse("search.html", {"request": request, "data": data})



@router.post("/wpsearchresults", response_class=HTMLResponse)
async def searchrequest(request: Request, 
                        creativework: TargetState = Form(...), 
                        dataset: TargetState = Form(...), 
                        software: TargetState = Form(...),
                        reproduce: ActionState = Form(...), 
                        distribute: ActionState = Form(...), 
                        modify: ActionState = Form(...), 
                        derive: ActionState = Form(...), 
                        commercial_use: ActionState = Form(...), 
                        charge_distribution_fee: ActionState = Form(...), 
                        change_license: ActionState = Form(...), 
                        share_alike: DutyState = Form(...)):
    """
    Handles the search request on the Wordpress search page and returns search results.

    Args:
        request (Request): The HTTP request object.
        creativework, dataset, software (TargetState): Filters for types of targets (creative work, dataset, software).
        reproduce, distribute, modify, derive, commercial_use, charge_distribution_fee, change_license (ActionState): Filters for actions associated with the license.
        share_alike (DutyState): Filter for the share alike duty.

    Returns:
        HTMLResponse: The rendered HTML template with the search results.
    """

    # Check if at least one type of target is selected, otherwise return to the search page
    if not creativework and not dataset and not software:
        # Return to the search page with an error message if no target type is selected
        return templates.TemplateResponse("wpsearch.html", {"request": request})

    # Construct the search facets based on the form inputs
    facets = LicenseSearch(
        target=TargetSearch(
            creativework=creativework,
            dataset=dataset,
            software=software
        ),
        actions=ActionsSearch(
            reproduce=reproduce,
            distribute=distribute,
            modify=modify,
            derive=derive,
            commercial_use=commercial_use,
            charge_distribution_fee=charge_distribution_fee,
            change_license=change_license
        ),
        duties=DutiesSearch(
            # Initializing all duty states to 'not applicable' by default
            distribute_duty_attribution=DutyState.na,
            distribute_duty_notice=DutyState.na,
            distribute_duty_source_code=DutyState.na,
            modify_duty_rename=DutyState.na,
            modify_duty_attribution=DutyState.na,
            modify_duty_modification_notice=DutyState.na,
            modify_duty_notice=DutyState.na,
            modify_duty_source_code=DutyState.na,
            derive_duty_rename=DutyState.na,
            derive_duty_attribution=DutyState.na,
            derive_duty_modification_notice=DutyState.na,
            derive_duty_notice=DutyState.na,
            derive_duty_source_code=DutyState.na),
        license_wide_duties=LicenseWideDutiesSearch(share_alike=share_alike)
    )
    
    # Perform the faceted search with the specified filters
    data = faceted_search(facets)

    # Return the search results rendered in the Wordpress search HTML template
    return templates.TemplateResponse("wpsearch.html", {"request": request, "data": data})


@router.get("/", response_class=HTMLResponse)
def html_index(request: Request):
    return templates.TemplateResponse("empty.html", {"request": request})
