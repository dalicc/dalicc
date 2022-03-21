from fastapi import FastAPI
from .routers import reasoner

app = FastAPI()

app.include_router(reasoner.router)