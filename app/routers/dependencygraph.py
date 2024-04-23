from fastapi import APIRouter, Body, HTTPException
from typing import Optional, Any
from pydantic import BaseModel
from enum import Enum
from SPARQLWrapper import SPARQLWrapper, JSON
from SPARQLBurger.SPARQLQueryBuilder import SPARQLGraphPattern, Triple, Filter
from rdflib import Graph
import simplejson as json
from typing import Any, Dict, AnyStr, List, Union, TypeVar
import requests
import os

# Setting up the FastAPI router with a specific prefix and tags
router = APIRouter(
    prefix="/dependencygraph",
    tags=["dependencygraph"],
    responses={404: {"description": "Not found"}},
)

# Initialize SPARQLWrapper with the endpoint
sparql = SPARQLWrapper(os.getenv('DB_URL'))

# Endpoint to get the dependency graph
@router.get("/list")
def get_dependency_graph(): 
    """
    Get the statements in the dependency graph.
    
    This function retrieves the entire dependency graph from a SPARQL endpoint.
    """
    # Setting the SPARQL query to retrieve data from the dependency graph
    sparql.setQuery("""
    PREFIX dp:<https://dalicc.net/dependencygraph/>

    SELECT * 
    FROM dp:dg_default
    WHERE { ?subject ?predicate ?object }
    """)

    # Setting the return format of the query result to JSON
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    # Returning the results in a structured format
    return {"dependency_graph_statements": results["results"]["bindings"]}