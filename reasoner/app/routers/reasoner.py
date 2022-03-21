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

#sparql = SPARQLWrapper("http://virtuoso-db:8890/sparql")


@router.get("/dependency_graph")
def dependency_graph():

    # create a random ID for the reasoning task (file)
    random_id = ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=5))
    lp_file = "./app/programs/temp/"+random_id+".lp"

    # create a temporary reasoning input file
    f = open(lp_file, "w")

    # run hexlite
    run_list = ["hexlite", "./app/programs/getdepgraph.lp",
                "--pluginpath", "./app/plugins", "--plugin", "plugins"]
    p = Popen(run_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()

    # transform reasoner output in list of triples
    if len(output) != 0:
        output_aux = output.decode(
            'UTF-8').split("{")[1].split("}")[0].split("),")
        output_aux_2 = list(map(lambda x: x.split(","), output_aux))
        output = list()
        for e in output_aux_2:
            if "license(" in e[0]:
                continue
            output.append([e[0].split("t(")[1], e[1], e[2]])

    # remove temporary reasoning input
    os.remove(lp_file)

    return output


@router.post("/compatibility")
def compatibility(input_json: Dict[Any, Any] = None):

    # create a temporary reasoning input file
    lp_file = "./app/programs/temp/test_user.lp"
    f = open(lp_file, "w")

    for license in input_json['licenses']:
        toWriteString = "license(\""+license+"\").\n"
        # print(toWriteString)
        f.write("license(\""+license+"\").\n")
    f.close()

    # command to run the reasoner hexlite with the input
    run_list = ["hexlite", lp_file, "./app/programs/query.lp",
                "--pluginpath", "./app/plugins", "--plugin", "plugins"]
    print(' '.join(run_list))

    p = Popen(run_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()

    terms_conflict_direct = []
    terms_conflict_derived = []
    if len(output) != 0:
        output_aux = output.decode(
            'UTF-8').split("{")[1].split("}")[0].split("),")

        for e in output_aux:
            if "directConflict(" in e:
                tmp_list = e.split("directConflict(")[1].split(',')
                tmp_list_2 = []
                for e2 in tmp_list:
                    if e2[-1] == ")":
                        tmp_list_2.append(e2[:-1].strip('"'))
                    else:
                        tmp_list_2.append(e2.strip('"'))
                terms_conflict_direct.append(list(tmp_list_2))
            if "derivedConflict(" in e:
                tmp_list = e.split("derivedConflict(")[1].split(',')
                tmp_list_2 = []
                for e2 in tmp_list:
                    if e2[-1] == ")":
                        tmp_list_2.append(e2[:-1].strip('"'))
                    else:
                        tmp_list_2.append(e2.strip('"'))
                terms_conflict_derived.append(list(tmp_list_2))

        return_dict = {"conflicting_statements": {"direct": {}, "derived": {}}}

        index = 0
        for e in terms_conflict_direct:
            l1 = e[0]
            d1 = e[1]
            a1 = e[2]
            l2 = e[3]
            d2 = e[4]
            a2 = e[5]
            s = {"statement_1": [e[0], e[1], e[2]], "statement_2": [
                e[3], e[4], e[5]], "reason": "Direct permission-prohibition conflict."}
            return_dict["conflicting_statements"]["direct"][str(index)] = s
            index += 1
        index = 0

        for e in terms_conflict_derived:
            l1 = e[0]
            d1 = e[1]
            a1 = e[2]
            l2 = e[3]
            d2 = e[4]
            a2 = e[5]
            dueTo = e[6]
            dueTo1 = e[7]
            dueTo2 = e[8]

            prefix_dict = {
                "odrl": "http://www.w3.org/ns/odrl/2/",
                "dalicc": "http://dalicc.net/ns#",
                "owl": "http://www.w3.org/2002/07/owl#"
            }

            p_dueTo = ""
            if "sameAs" in dueTo:
                p_dueTo = prefix_dict["owl"]
            elif "implies" in dueTo:
                p_dueTo = prefix_dict["odrl"]
            elif "contradicts" in dueTo:
                p_dueTo = prefix_dict["dalicc"]
            elif "includedIn" in dueTo:
                p_dueTo = prefix_dict["odrl"]

            if e[9] == 'derived':
                due_to_derived_or_graph = "is given in the dependency graph."
            else:
                due_to_derived_or_graph = "is derived from the statements in the dependency graph."
            s = {"statement_1": [l1, d1, a1], "statement_2": [
                l2, d2, a2], "reason": "Derived permission-prohibition conflict. "+"("+dueTo1+","+p_dueTo+dueTo+","+dueTo2+") "+due_to_derived_or_graph}
            return_dict["conflicting_statements"]["derived"][str(index)] = s
            index += 1

        return return_dict

    return output
