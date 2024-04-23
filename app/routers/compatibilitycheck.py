from xml.dom.minidom import Identified
from rdflib.term import Identifier
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

# Type aliases for JSON structures
JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]

# BaseModel for input JSON
class LicensesJSON(BaseModel):
    licenses: list = []

# Function to check if JSON is valid
def isAValidJSON(input_json):
    try:
        input_json[b'userID']
    except KeyError:
        return False, "Error: User ID is missing"
    return True, None

# API router configuration
router = APIRouter(
    prefix="/compatibilitycheck",
    tags=["compatibilitycheck"],
    responses={404: {"description": "Not found"}},
)

# SPARQL endpoint
sparql = SPARQLWrapper(os.getenv('DB_URL'))

# Endpoint for compatibility check
@router.post("/")
def compatibility(input_json: LicensesJSON = None): 
    """
    Compatibility check of multiple (2 or more) licenses that returns the conflicting statements.
    
    Request body examples:
    * {"licenses": ["https://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement","https://dalicc.net/licenselibrary/UkOpenGovernmentLicenseForPublicSectorInformation"]}
    * {"licenses": ["https://dalicc.net/licenselibrary/Apache-2.0", "https://dalicc.net/licenselibrary/MIT", "https://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement"]}
    """
    # Address for the compatibility reasoner
    reasoner_address = os.getenv('REASONER_URL')+"/compatibility"
    
    # Sending a POST request to the reasoner and returning the response
    response = requests.post(reasoner_address,  data = input_json.json())
    
    return response.json()