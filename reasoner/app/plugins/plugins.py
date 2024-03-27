import dlvhex
from SPARQLWrapper import SPARQLWrapper, JSON
import configparser

def getLicense(strs):
    """
    Retrieves license information based on a given string.

    Args:
        strs (tuple): Contains a string used to query the license information.

    Returns:
        Outputs license information as tuples.
    """

    # Read configurations from the 'reasoner.config' file
    config = configparser.ConfigParser()
    config.read('reasoner.config')
    sparql_endpoint = config['DEFAULT']['sparql_endpoint']

    # Set up a SPARQL wrapper with the endpoint from the configuration
    sparql = SPARQLWrapper(sparql_endpoint)

    # Define a SPARQL query to retrieve license information
    new_query = """
    PREFIX odrl: <http://www.w3.org/ns/odrl/2/>
    SELECT DISTINCT ?s ?p ?o
    WHERE {
        ?s ?p ?o1.
        ?o1 odrl:action ?o.        
        FILTER (?s = <""" + str(strs[0]).strip('"') + """>) .
        FILTER (?p IN (odrl:permission, odrl:prohibition, odrl:obligation, odrl:duty) ).
    }
    """

    # Execute the query and get results
    sparql.setQuery(new_query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    # Process the results into triples
    triples = []
    for e in results["results"]["bindings"]:
        triples.append([e['s']['value'], e['p']['value'], e['o']['value']])

    # Output each triple
    for t in triples:
        dlvhex.output((t[0], t[1], t[2],))

    return

def concat(strs):
    """
    Concatenates a tuple of strings into a single string.

    Args:
        strs (tuple): A tuple containing strings to be concatenated.

    Returns:
        Outputs the concatenated string.
    """
    
    # Determine if any of the strings need quoting
    needquote = any(['"' in s.value() for s in strs])
    unquoted = [s.value().strip('"') for s in strs]
    result = ''.join(unquoted)
    if needquote:
        result = '"'+result+'"'
    
    # Output the concatenated result
    dlvhex.output((dlvhex.storeConstant(result),))

def getDependencyGraph(dp_named_graph):
    """
    Retrieves dependency graph information.

    Args:
        dp_named_graph (str): The named graph in the SPARQL endpoint to query.

    Returns:
        Outputs the dependency graph as tuples.
    """

    # Read configurations from the 'reasoner.config' file
    config = configparser.ConfigParser()
    config.read('reasoner.config')
    sparql_endpoint = config['DEFAULT']['sparql_endpoint']

    # Set up a SPARQL wrapper with the endpoint from the configuration
    sparql = SPARQLWrapper(sparql_endpoint)

    # Define and execute a SPARQL query to retrieve the dependency graph
    sparql.setQuery("""
    PREFIX dp: <https://dalicc.net/dependencygraph/>
    SELECT * 
    FROM dp:"""+str(dp_named_graph).strip('"')+"""
    WHERE { ?s ?p ?o }
    """)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    # Process the results into triples
    triples = []
    for e in results["results"]["bindings"]:
        triples.append([e['s']['value'], e['p']['value'], e['o']['value']])

    # Output each triple
    for t in triples:
        dlvhex.output((t[0], t[1], t[2],))
    return

def register(arguments=None):
    """
    Registers custom atoms for use in dvlhex.

    Args:
        arguments: Optional arguments for the registration process.
    """

    # Setting up properties for external source
    prop = dlvhex.ExtSourceProperties()
    prop.addFiniteOutputDomain(0)

    # Registering custom atoms with specific arity
    dlvhex.addAtom("getLicense", (dlvhex.TUPLE,), 3, prop)
    dlvhex.addAtom("concat", (dlvhex.TUPLE,), 1, prop)
    dlvhex.addAtom("getDependencyGraph", (dlvhex.CONSTANT,), 3, prop)