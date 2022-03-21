import dlvhex
from SPARQLWrapper import SPARQLWrapper, JSON
import configparser


def getLicense(strs):
    config = configparser.ConfigParser()
    config.read('reasoner.config')
    # "http://virtuoso-db:8890/sparql"#
    sparql_endpoint = config['DEFAULT']['sparql_endpoint']

    sparql = SPARQLWrapper(sparql_endpoint)

    # query for finding license via string
    """
	PREFIX rdf:	<http://www.w3.org/1999/02/22-rdf-syntax-ns#>
	PREFIX odrl:	<http://www.w3.org/ns/odrl/2/>
	PREFIX dct:	<http://purl.org/dc/terms/>
	PREFIX ns3:	<http://www.statcan.gc.ca/eng/reference/>
	PREFIX cc:	<http://creativecommons.org/ns#>
	PREFIX dalicc:	<http://dalicc.net/ns#>

	SELECT DISTINCT ?s ?p ?o
	WHERE
	{
	{
	?s rdf:type odrl:Set . 
	?s dct:alternative|dct:title ?licenseName .
	?s ?p ?o.
	?o rdf:type ?t. 
	FILTER (?licenseName = "Apache License 2.0") .
	FILTER (?t IN (odrl:Permission, odrl:Prohibition, odrl:Duty) ).
	}
	}
	"""
    # new query gets triples via URI
    new_query = """
	PREFIX odrl:	<http://www.w3.org/ns/odrl/2/>
	SELECT DISTINCT ?s ?p ?o
	WHERE
	{
	?s ?p ?o1.
	?o1 odrl:action ?o.		
	FILTER (?s = <""" + str(strs[0]).strip('"') + """>) .
	FILTER (?p IN (odrl:permission, odrl:prohibition, odrl:obligation, odrl:duty) ).
	}
	"""

    sparql.setQuery(new_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    triples = list()

    for e in results["results"]["bindings"]:
        triples.append([e['s']['value'], e['p']['value'], e['o']['value']])

    for t in triples:
        dlvhex.output((t[0], t[1], t[2],))

    return


def concat(strs):
    needquote = any(['"' in s.value() for s in strs])
    unquoted = [s.value().strip('"') for s in strs]
    result = ''.join(unquoted)
    if needquote:
        result = '"'+result+'"'
    dlvhex.output((dlvhex.storeConstant(result),))


def getDependencyGraph(dp_named_graph):
    config = configparser.ConfigParser()
    config.read('reasoner.config')

    sparql_endpoint = config['DEFAULT']['sparql_endpoint']

    sparql = SPARQLWrapper(sparql_endpoint)

    sparql.setQuery("""
	PREFIX dp:	<http://dalicc.net/dependencygraph/>

	SELECT * 
	FROM dp:"""+str(dp_named_graph).strip('"')+"""
	WHERE { ?s ?p ?o }

	""")
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    triples = list()

    for e in results["results"]["bindings"]:
        triples.append([e['s']['value'], e['p']['value'], e['o']['value']])

    for t in triples:
        dlvhex.output((t[0], t[1], t[2],))
    return


def register(arguments=None):
    prop = dlvhex.ExtSourceProperties()
    prop.addFiniteOutputDomain(0)
    dlvhex.addAtom("getLicense", (dlvhex.TUPLE,), 3, prop)
    dlvhex.addAtom("concat", (dlvhex.TUPLE,), 1, prop)
    dlvhex.addAtom("getDependencyGraph", (dlvhex.CONSTANT,), 3, prop)
