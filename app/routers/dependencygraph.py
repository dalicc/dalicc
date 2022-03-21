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

router = APIRouter(
    prefix="/dependencygraph",
    tags=["dependencygraph"],
    responses={404: {"description": "Not found"}},
)
sparql = SPARQLWrapper("http://virtuoso-db:8890/sparql")

@router.get("/list")
def get_dependency_graph(): 
    """
    Get the statements in the dependency graph.
    """
    # Check if the input_json has everything needed for this task
    sparql.setQuery("""
	PREFIX dp:<http://dalicc.net/dependencygraph/>

	SELECT * 
	FROM dp:dg_default
	WHERE { ?subject ?predicate ?object }
	""")
    
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    
    rDict = dict()
    return {"dependency_graph_statements":results["results"]["bindings"]}

