from xml.dom.minidom import Identified
from SPARQLWrapper.Wrapper import CSV, TURTLE
from rdflib.term import Identifier
from fastapi import APIRouter, Body  # , httpException
from typing import Optional, Any
from pydantic import BaseModel
from enum import Enum
from SPARQLWrapper import SPARQLWrapper, JSON
from SPARQLBurger.SPARQLQueryBuilder import SPARQLGraphPattern, Triple, Filter
from rdflib import Graph
import simplejson as json
from typing import Any, Dict, AnyStr, List, Union, TypeVar
import requests

JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]


router = APIRouter(
    prefix="/licenselibrary",
    tags=["licenselibrary"],
    responses={404: {"description": "Not found"}},
)
sparql = SPARQLWrapper("http://virtuoso-db:8890/sparql")


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


@router.get("/license/{license_id}")
def get_license_by_id(license_id):
    """
    Get the machine-readable representation of the license from the DALICC license library.
    
    The range of the license URIs can be listed via the **licenselibrary/list** endpoint.

    Parameters:
    * _license\_id_: (type: _string_) 
        * E.g.: **Apache-2.0**, **0BSD**, **MIT**, **MS-PL**, **CC-BY-NC-SA-4.0**, **CC-BY-3.0-NL**, **CC-BY-4.0**

    """
    g = Graph()
    try:
        g.parse("licensedata/licenses/"+license_id+".ttl", format="ttl")
    except:
        pass
    response = json.loads(g.serialize(format="json-ld"))
    return(response)


@router.get("/list")
def list_licenses_in_the_license_library(keyword: Optional[str] = None, skip: Optional[int] = 0, limit: Optional[int] = 10):
    """
    Get the list of the licenses (_URI_ and _title_) stored in the license library.

    *  Parameters:
        * _keyword_: (type: _string_) Title of the license contains _keyword_.
        * _skip_: (type: _int_) Offsets the results by given value for paging.
        * _limit_: (type: _int_) Limits the number of returned results.
    """
    q = keyword
    if q:
        q_part_t = "FILTER CONTAINS(LCASE(?title),\""+str(q).lower()+"\").\n"
        q_part_a = "FILTER CONTAINS(LCASE(?title_alternative),\"" + \
            str(q).lower()+"\").\n"
    else:
        q_part_t = ""
        q_part_a = ""

    query = """
     PREFIX dct: <http://purl.org/dc/terms/> 
        PREFIX odrl: <http://www.w3.org/ns/odrl/2/> 
        PREFIX dcmitype: <http://purl.org/dc/dcmitype/> 
        PREFIX dalicc: <http://dalicc.net/ns#> 
        PREFIX cc: <http://creativecommons.org/ns#> 
        SELECT DISTINCT ?id ?title FROM <http://dalicc.net/licenselibrary/> 
        WHERE {
{
?id rdf:type odrl:Set.
?id dct:title ?title.\n"""+q_part_t+"""
}
UNION
{
?id rdf:type odrl:Set.
?id dct:title ?title.
?id dct:alternative ?title_alternative.\n"""+q_part_a+"""}
}
        ORDER BY ASC(?title)
        LIMIT """+str(limit)+"""
        OFFSET """+str(skip)

    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    return(results)


@router.post("/facetedsearch")
def faceted_search(facets: LicenseSearch, skip: Optional[int] = 0, limit: Optional[str] = 10) -> dict:
    """
    Search for licenses that satisfy certain criteria.

    Request body:
    * request[**"target"**][...]: (type: _TargetState_) **"yes" / "no"**
    * request[**"actions"**][...]: (type: _ActionState_) **"na" / "permitted" / "prohibited"**
    * request[**"duties"**][...]: (type: _DutyState_) **"na" / "required"**
    * request[**"license_wide_duties"**][...]: (type: _DutyState_) **"na" / "required"**

    Parameters:
    * _skip_: (type: _int_) Offsets the results by given value for paging.
    * _limit_: (type: _int_) Limits the number of returned results.
    """

    if limit == 10:
        limit = 1000

    duty_map = {"attribution": "cc:Attribution",
                "notice": "cc:Notice",
                "source_code": "cc:SourceCode",
                "rename": "dalicc:rename",
                "modification_notice": "dalicc:modificationNotice",
                "compliant_license": "dalicc:compliantLicense",
                "share_alike": "cc:ShareAlike"}

    action_map = {"reproduce": "odrl:reproduce",
                  "distribute": "odrl:distribute",
                  "modify": "odrl:modify",
                  "derive": "odrl:derive",
                  "commercial_use": "cc:CommercialUse",
                  "charge_distribution_fee": "dalicc:chargeDistributionFee",
                  "change_license": "dalicc:ChangeLicense",
                  "share_alike": "cc:ShareAlike"}

    p_map = action_map.copy()

    for kd in duty_map:
        for ka in action_map:
            p_map[ka+"_duty_"+kd] = duty_map[kd]

    prefixes = """PREFIX dct: <http://purl.org/dc/terms/> 
PREFIX odrl: <http://www.w3.org/ns/odrl/2/> 
PREFIX dcmitype: <http://purl.org/dc/dcmitype/> 
PREFIX dalicc: <http://dalicc.net/ns#> 
PREFIX cc: <http://creativecommons.org/ns#> 
"""

    no_action_selected = True
    for p, value in facets.actions:
        if value != ActionState.na:
            no_action_selected = False

    in_clause = "("

    provenance_clause = "?id dct:type "
    provenance_query_clause = ""
    provenance_not_exist_clause = ""

    for c, target in [("dalicc:CreativeWork", facets.target.creativework), ("dcmitype:Dataset", facets.target.dataset), ("dcmitype:Software", facets.target.software)]:
        if target == TargetState.true:
            in_clause = in_clause + c + ","
            provenance_query_clause = provenance_query_clause + provenance_clause + c + ".\n"
        if target == TargetState.false:
            provenance_not_exist_clause += "FILTER NOT EXISTS{\n ?asset dct:type " + c + ".\n}\n"

    in_clause = in_clause[:-1]
    in_clause += ")"
    in_clause = "FILTER (?assettype IN " + in_clause + ")."
    if (facets.target.creativework == facets.target.dataset == facets.target.software == TargetState.false):
        in_clause = ""

    if no_action_selected:
        sa_addition = ""
        if facets.license_wide_duties.share_alike == DutyState.required:
            p_cur_id = 1000
            d_cur_id = 1001
            sa_addition += "?id odrl:duty "+"?d" + \
                str(d_cur_id)+". \n ?d"+str(d_cur_id) + \
                " odrl:action "+p_map["share_alike"]+".\n"

        query = """SELECT DISTINCT ?id ?title FROM <http://dalicc.net/licenselibrary/> 
                WHERE
                { {
                ?id odrl:target ?asset.
                ?id dct:title ?title.
                ?asset dct:type ?assettype.
                """+sa_addition+"""
                }
                """+in_clause+"""
                """+provenance_not_exist_clause+"""
                }"""
        print(prefixes+query)
        sparql.setQuery(prefixes+query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results

    permission_once = True
    prohibition_once = True

    query = "SELECT DISTINCT ?id ?title FROM <http://dalicc.net/licenselibrary/> \nWHERE\n{\n{"

    p_set = set(map(str, range(1, 15)))
    d_set = set(map(str, range(1, 150)))
    query += "?id dct:title ?title.\n"
    for p, value in facets.actions:
        p_cur_id = p_set.pop()

        if value == ActionState.permitted:

            query += "?id odrl:permission ?p" + \
                str(p_cur_id)+". \n ?p"+str(p_cur_id) + \
                " odrl:action "+p_map[p]+".\n"
            for d, value_d in facets.duties:
                d_cur_id = d_set.pop()
                if p in d and value_d == DutyState.required:
                    query += "?p"+str(p_cur_id)+" odrl:duty "+"?d"+str(d_cur_id) + \
                        ". \n ?d"+str(d_cur_id)+" odrl:action "+p_map[d]+".\n"
            if permission_once:
                query += "?id"+" odrl:target ?asset.\n ?asset dct:type ?assettype."
                permission_once = False

        elif value == ActionState.prohibited:
            query += "?id odrl:prohibition ?p" + \
                str(p_cur_id)+". \n ?p"+str(p_cur_id) + \
                " odrl:action "+p_map[p]+".\n"
            if prohibition_once:
                query += "?id"+" odrl:target ?asset.\n ?asset dct:type ?assettype."
                prohibition_once = False

    if facets.license_wide_duties.share_alike == DutyState.required:
        d_cur_id = d_set.pop()
        query += "?id odrl:duty "+"?d" + \
            str(d_cur_id)+". \n ?d"+str(d_cur_id) + \
            " odrl:action "+p_map["share_alike"]+".\n"

    query += "}"+in_clause+"\n"+provenance_not_exist_clause
    query += """}"""

    print(prefixes+query)
    sparql.setQuery(prefixes+query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results


@router.post("/composer")
def composer(input_license: Any = Body(..., media_type="text/turtle")) -> dict:
    return
    # to be enabled later
    try:
        g = Graph().parse(data=input_license, format="turtle")
        triples = g.serialize(format="nt").decode('UTF-8')
        query = f"""
            INSERT DATA {{ GRAPH <http://dalicc.net/licenselibrary/> {{ {triples} }} }}
        """
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()
        return results

    except Exception as e:
        raise httpException(status_code=422, detail=str(e))


def isAValidJSON(input_json):
    try:
        input_json[b'userID']
    except KeyError:
        return False, "Error: User ID is missing"
    return True, None
