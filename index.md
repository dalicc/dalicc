# DALICC API #

DALICC API supports the automated clearance of rights thus supporting the legally secure and time-efficient reutilization of third party data sources. The services are running [here](https://api.dalicc.net/docs). 

## Instructions ###

### RDF Data ####

* license-library.ttl
* license-library-meta.ttl

### Requirements ####

* docker
* docker-compose

### Setup ###

* `docker-compose build --pull`
* `docker-compose up -d`

### Virtuoso Configuration ###

* Virtuoso is hosted using [this Docker image](https://hub.docker.com/r/tenforce/virtuoso/).
* The Virtuoso DB is available at port `8890`; see [docker-compose.yml](docker-compose.yml) for configurations.
* The database files are stored in a local volume in `virtuoso_data`

##### Load Data #####

* Copy RDF files into `dumps` directory and specify the graph:
    1. `cp rdf/* virtuoso_data/.`
    2. `echo "https://dalicc.net/license-library/" > license-library.ttl.graph`
    3. `echo "https://dalicc.net/license-library-meta/" > license-library-meta.ttl.graph`
* To load RDF files into Virtuoso follow the instructions from the [documentation](http://vos.openlinksw.com/owiki/wiki/VOS/VirtBulkRDFLoader): 
    1. `docker exec -it virtuoso-db bash`
    2. `isql-v -U dba -P dba`
    3. `SQL> ld_dir('dumps', '*.ttl', NULL);`
    4. `SQL> rdf_loader_run();`

##### Full Text Index #####

* Build a full text index over the graph:
    1. `docker exec -it virtuoso-db bash`
    2. `isql-v -U dba -P dba`
    3. -- We specify that all string objects in the graph 'license-library' should be text indexed:
        * `SQL> DB.DBA.RDF_OBJ_FT_RULE_ADD('https://dalicc.net/license-library/', null, 'licenses');`
    4. -- We update the text index.
        * `SQL> DB.DBA.VT_INC_INDEX_DB_DBA_RDF_OBJ ();`
* To set the text index to follow the triples in real time, use:
    * `DB.DBA.VT_BATCH_UPDATE ('DB.DBA.RDF_OBJ', 'OFF', null);`
* To set the text index to be updated every 10 minutes, use:
    * `DB.DBA.VT_BATCH_UPDATE ('DB.DBA.RDF_OBJ', 'ON', 10);`
* Example query using the full text index:
    * `SELECT * FROM <https://dalicc.net/license-library/> WHERE { ?s ?p ?o . ?o bif:contains '"Mozilla*"'};`
    
### API Configuration ###

* The API is implemented using [FastAPI](https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker).
* The source files of the API are in [app](app); FastAPI reloads the application on any local changes.

##### Endpoint #####

* The Swagger documentation is avaliable at [localhost:8090/docs](http://localhost:8090/docs)
