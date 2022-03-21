from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from .routers import compatibilitycheck, dependencygraph, licenselibrary
from starlette.responses import FileResponse

app = FastAPI()
app_custom_openapi = FastAPI()

app.include_router(licenselibrary.router)
app.include_router(dependencygraph.router)
app.include_router(compatibilitycheck.router)

app_custom_openapi.include_router(licenselibrary.router)
app_custom_openapi.include_router(dependencygraph.router)
app_custom_openapi.include_router(compatibilitycheck.router)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="DALICC API",
        version="1.0 alpha release",
        description="Data Licenses Clearance Center API",
        routes=app_custom_openapi.routes,
    )
    openapi_schema["paths"]["/licenselibrary/composer"]["post"] = {}
    openapi_schema["paths"]["/licenselibrary/composer"]["post"]["tags"] = [
        "licenselibrary"
    ]
    openapi_schema["paths"]["/licenselibrary/composer"]["post"]["summary"] = "[𝙐𝙉𝘿𝙀𝙍 𝘿𝙀𝙑𝙀𝙇𝙊𝙋𝙈𝙀𝙉𝙏]"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

