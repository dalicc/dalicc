# Importing necessary modules and classes
from xml.dom.minidom import Identified
from rdflib.term import Identifier
from app.routers import dependencygraph
from fastapi import APIRouter, Body, HTTPException
from typing import Optional, Any
from pydantic import BaseModel
from enum import Enum
from SPARQLWrapper import SPARQLWrapper, JSON
from SPARQLBurger.SPARQLQueryBuilder import SPARQLGraphPattern, Triple, Filter
from rdflib import Graph
import json
from typing import Any, Dict, AnyStr, List, Union, TypeVar
import requests
import os

# Type aliases for JSON related data structures
JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]

# Pydantic model for Licenses JSON structure
class LicensesJSON(BaseModel):
    licenses: list = []

# Pydantic model for Reasoner Task input structure
class ReasonerTask(BaseModel):
    license_input: list = []
    dependency_graph: list = []

# Function to check if the input JSON is valid
def isAValidJSON(input_json):
    try:
        # Attempt to access 'userID' key in the JSON
        input_json[b'userID']
    except KeyError:
        # If 'userID' key is missing, return False with an error message
        return False, "Error: User ID is missing"
    # If 'userID' key exists, return True with None as error message
    return True, None

# Creating an API router for the reasoner functionality
router = APIRouter(
    prefix="/reasoner",  # Prefix for the route
    tags=["reasoner"],   # Tags for grouping endpoints
    responses={404: {"description": "Not found"}},  # Default responses
)

# Initializing the SPARQL wrapper with the endpoint URL
sparql = SPARQLWrapper(os.getenv('DB_URL'))

# Endpoint for the reasoner function
@router.post("/")
def reasoner(input_json: ReasonerTask = None): 
    """    
    Accepts JSON input containing license statements and dependency graph.

    Args:
        input_json (ReasonerTask): The input data for the reasoner.

    Returns:
        JSON response from the reasoner service.
    """
    
    # Address of the reasoner service
    reasoner_address = os.getenv('REASONER_URL')+"/ws"
    
    # Sending a POST request to the reasoner service and returning the response
    response = requests.post(reasoner_address, data=input_json.json())
    
    return response.json()