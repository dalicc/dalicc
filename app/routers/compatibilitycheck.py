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

JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]

class LicensesJSON(BaseModel):
    licenses: list = []

def isAValidJSON(input_json):
    try:
        input_json[b'userID']
    except KeyError:
        print(input_json)
        return False,"Error: User ID is missing"
    return True,None


router = APIRouter(
    prefix="/compatibilitycheck",
    tags=["compatibilitycheck"],
    responses={404: {"description": "Not found"}},
)
sparql = SPARQLWrapper("http://virtuoso-db:8890/sparql")

@router.post("/")
def compatibility(input_json: LicensesJSON = None): 
    """
    Compatibility check of multiple (2 or more) licenses that returns the conflicting statements.
    
    Request body:
    * request["licenses"][...]: (type: _licenseURI_)
        * E.g. 1: {"licenses": ["http://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement","http://dalicc.net/licenselibrary/UkOpenGovernmentLicenseForPublicSectorInformation"]}
        * E.g. 2: {"licenses": ["http://dalicc.net/licenselibrary/Apache-2.0", "http://dalicc.net/licenselibrary/MIT"]}
        * E.g. 3: {"licenses": ["http://dalicc.net/licenselibrary/Apache-2.0", "http://dalicc.net/licenselibrary/MIT", "http://dalicc.net/licenselibrary/StatisticsCanadaOpenLicenceAgreement"]}
    """
    
    reasoner_address = "http://dalicc-reasoner:80/reasoner/compatibility"
    
    response = requests.post(reasoner_address,  data = input_json.json())
    
    return response.json()