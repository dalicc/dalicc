import json
import requests
from fastapi import FastAPI, HTTPException
from fastapi import APIRouter, Body, HTTPException

# Configuration (commented out)
LIBRARIES_URL = "https://libraries.io/api/"
DALICC_URL = "https://api.dalicc.net/"

# Configuring the API router with specific settings
router = APIRouter(
    prefix="/githublicensechecker",
    tags=["githublicensechecker"],
    responses={404: {"description": "Not found"}},
)

# Function to look up a license in DALICC
def dalicc_lookup(license_id: str):
    api_url = DALICC_URL + "licenselibrary/license/{license_id}?format=json-ld&download=false".format(license_id=license_id)
    response = requests.get(api_url)
    dalicc_res = response.json()
    try:
        if dalicc_res and "@graph" in dalicc_res and "@id" in dalicc_res["@graph"]:
            dalicc_id = dalicc_res["@graph"]["@id"]
            return dalicc_id
        else:
            return None
    except:
        print("::: Error with retrieving license ", license_id,". Got ", dalicc_res)
        return None

# Function to parse GitHub repository URL and extract owner and name
def parse_github_url(github_url: str):
    github_url = github_url.replace("https://github.com/", "")
    if "?" in github_url:
        github_url = github_url.split("?")[0]
    if not "/" in github_url:
        raise HTTPException(status_code=400, detail="The input is not a valid Github repository: owner/name")
    s = github_url.split("/")
    owner = s[0]
    name = s[1]
    return owner, name

# Function to check license compatibility using DALICC
def dalicc_compatibility(licenses: list):
    api_url = DALICC_URL + "compatibilitycheck/"
    body = json.dumps({"licenses": licenses})
    response = requests.post(api_url, data=body)
    dalicc_res = response.json()
    return dalicc_res

# Endpoint to get repository dependencies by owner and name
@router.get("/dependencies/{owner}/{name}")
def repository_dependencies(owner: str, name: str):
    api_url = LIBRARIES_URL + "github/{owner}/{name}/dependencies".format(owner=owner, name=name)
    response = requests.get(api_url)
    lib_res = response.json()
    return lib_res

# Endpoint to get repository dependencies by URL
@router.get("/dependencies")
def repository_dependencies_by_url(github_url: str):
    owner, name = parse_github_url(github_url)
    return repository_dependencies(owner, name)

# Endpoint to check compatibility of repository dependencies
@router.get("/check/{owner}/{name}")
def check_repository_dependencies(owner: str, name: str):
    dependencies = repository_dependencies(owner, name)
    comp_check = []
    result = {"dependencies": [], "name": dependencies["full_name"], "language": dependencies["language"]}
    for d in dependencies["dependencies"]:
        if "normalized_licenses" in d and d["normalized_licenses"] and len(d["normalized_licenses"]) > 0:
            for l in d["normalized_licenses"]:
                dalicc_id = dalicc_lookup(l)
                if dalicc_id:
                    comp_check.append(dalicc_id)
                result["dependencies"].append({"name": d["name"], "license": l, "dalicc_id": dalicc_id})
    
    result["compatibilitycheck"] = dalicc_compatibility(comp_check)
    return result

# Endpoint to check compatibility of repository dependencies by URL
@router.get("/check")
def check_repository_dependencies_by_url(github_url: str):
    owner, name = parse_github_url(github_url)
    return check_repository_dependencies(owner, name)