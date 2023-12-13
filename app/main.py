from fastapi import FastAPI, File, UploadFile
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from .routers import compatibilitycheck, reasoner, dependencygraph, licenselibrary, web, githublicensechecker
from starlette.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Create an instance of the FastAPI application
app = FastAPI()

# Create another FastAPI instance for custom OpenAPI schema
app_custom_openapi = FastAPI()

# Define the list of origins that are allowed to communicate with the API
origins = [
    "http://localhost",
    "http://localhost:8080",
]


# Add CORS (Cross-Origin Resource Sharing) middleware to the application
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Include various routers from different modules
app.include_router(licenselibrary.router)
app.include_router(web.router)
app.include_router(dependencygraph.router)
app.include_router(compatibilitycheck.router)
app.include_router(githublicensechecker.router)

# Include routers in the custom OpenAPI application
app_custom_openapi.include_router(licenselibrary.router)
app_custom_openapi.include_router(dependencygraph.router)
app_custom_openapi.include_router(compatibilitycheck.router)
app_custom_openapi.include_router(githublicensechecker.router)

# Mount static files to the application
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Route to return the respec html page
@app.get("/spec")
async def read_index():
    return FileResponse('app/static/spec/index.html')

# Function to create a custom OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="DALICC API",
        version="1.0",
        description="Data Licenses Clearance Center API",
        routes=app_custom_openapi.routes,
    )
    
    # Customize specific parts of the OpenAPI schema
    openapi_schema["paths"]["/licenselibrary/composer"]["post"] = {}
    openapi_schema["paths"]["/licenselibrary/composer"]["post"]["tags"] = ["licenselibrary"]
    openapi_schema["paths"]["/licenselibrary/composer"]["post"]["summary"] = "License Composer"
    openapi_schema["paths"]["/licenselibrary/composer"]["post"]["description"] = "Please get in touch at info@dalicc.net to receive the usage instructions and your personalized access token."
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Set the custom OpenAPI function to the application
app.openapi = custom_openapi