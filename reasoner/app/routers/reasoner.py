from fastapi import APIRouter
import simplejson as json
import subprocess
from subprocess import Popen, PIPE
import os
from pydantic import BaseModel
import random
import string

from typing import Any, Dict, AnyStr, List, Union, Optional

JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]

router = APIRouter(
    prefix="/reasoner",
    tags=["reasoner"],
    responses={404: {"description": "Not found"}},
)

class LicensesJSON(BaseModel):
    licenses: list = []

# Endpoint to retrieve the dependency graph
@router.get("/dependency_graph")
def dependency_graph():
    """
    Endpoint to retrieve a dependency graph.

    Returns:
        A list of triples representing the dependency graph.
    """
    # Generate a random file name for temporary storage
    random_id = ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=5))
    lp_file = "./app/programs/temp/" + random_id + ".lp"

    # Create and write to a temporary file
    with open(lp_file, "w") as f:
        pass

    # Run hexlite to process the logic program
    run_list = ["hexlite", "./app/programs/getdepgraph.lp",
                "--pluginpath", "./app/plugins", "--plugin", "plugins"]
    p = Popen(run_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()

    # Process the output into a list of triples
    triples = []
    if len(output) != 0:
        output_aux = output.decode('UTF-8').split("{")[1].split("}")[0].split("),")
        output_aux_2 = list(map(lambda x: x.split(","), output_aux))
        for e in output_aux_2:
            if "license(" in e[0]:
                continue
            triples.append([e[0].split("t(")[1], e[1], e[2]])

    # Remove the temporary file
    os.remove(lp_file)

    return triples

def process_conflict_term(conflict_string):
    """
    Processes a conflict term string to extract relevant information.

    Args:
        conflict_string (str): A string representing a conflict term from hexlite output.

    Returns:
        list: A list containing processed elements of the conflict term.
    """
    # Splitting the string to isolate the components of the conflict term
    elements = conflict_string.split('(')[1].split(',')
    processed_elements = []

    # Processing each element in the conflict term
    for element in elements:
        # Remove closing parenthesis and strip quotes
        clean_element = element.rstrip(')').strip('"')
        processed_elements.append(clean_element)

    return processed_elements

def compile_conflict_results(direct_conflicts, derived_conflicts):
    """
    Compiles direct and derived conflict information into a structured dictionary.

    Args:
        direct_conflicts (list): A list of direct conflict terms.
        derived_conflicts (list): A list of derived conflict terms.

    Returns:
        dict: A dictionary containing structured conflict information.
    """
    conflict_dict = {"conflicting_statements": {"direct": {}, "derived": {}}}

    # Process direct conflicts
    for index, conflict in enumerate(direct_conflicts):
        statement_1 = conflict[:3]  # First half of the conflict term
        statement_2 = conflict[3:6]  # Second half of the conflict term
        conflict_dict["conflicting_statements"]["direct"][str(index)] = {
            "statement_1": statement_1,
            "statement_2": statement_2,
            "reason": "Direct permission-prohibition conflict."
        }

    # Process derived conflicts
    for index, conflict in enumerate(derived_conflicts):
        statement_1 = conflict[:3]  # First half of the conflict term
        statement_2 = conflict[3:6]  # Second half of the conflict term
        due_to_reason = determine_due_to_reason(conflict[6:])  # Additional reasoning info
        conflict_dict["conflicting_statements"]["derived"][str(index)] = {
            "statement_1": statement_1,
            "statement_2": statement_2,
            "reason": f"Derived permission-prohibition conflict. {due_to_reason}"
        }

    return conflict_dict

def determine_due_to_reason(additional_info):
    """
    Determines the reason for a conflict based on additional information.

    Args:
        additional_info (list): Additional information elements from a derived conflict term.

    Returns:
        str: A string describing the reason for the conflict.
    """
    # Example logic to determine the reason based on additional info
    # This can be modified based on the specific format of the additional info
    if 'derived' in additional_info:
        return "is derived from the statements in the dependency graph."
    else:
        return "is given in the dependency graph."


# Endpoint to check the compatibility of licenses
@router.post("/compatibility")
def compatibility(input_json: Dict[Any, Any] = None):
    """
    Endpoint for checking compatibility between multiple licenses.

    Args:
        input_json (Dict[Any, Any]): Input JSON containing a list of licenses.

    Returns:
        A dictionary detailing conflicts between licenses, if any.
    """

    # Create a temporary file for reasoning input
    lp_file = "./app/programs/temp/test_user.lp"
    with open(lp_file, "w") as f:
        for license in input_json['licenses']:
            f.write(f"license(\"{license}\").\n")

    # Command to run the reasoner hexlite with the input file
    run_list = ["hexlite", lp_file, "./app/programs/query.lp",
                "--pluginpath", "./app/plugins", "--plugin", "plugins"]

    # Execute the command and capture the output
    p = Popen(run_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()

    # Initialize lists to store direct and derived conflicts
    terms_conflict_direct = []
    terms_conflict_derived = []

    # Process the output if it's not empty
    if len(output) != 0:
        output_aux = output.decode('UTF-8').split("{")[1].split("}")[0].split("),")

        # Extract conflict terms from the output
        for e in output_aux:
            if "directConflict(" in e:
                terms_conflict_direct.append(process_conflict_term(e))
            if "derivedConflict(" in e:
                terms_conflict_derived.append(process_conflict_term(e))

        # Compile results into a structured return dictionary
        return_dict = compile_conflict_results(terms_conflict_direct, terms_conflict_derived)

        return return_dict

    return output
