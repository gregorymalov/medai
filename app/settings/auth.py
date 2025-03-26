import os
# from mlab_amo_async import tokens
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
# from openai import OpenAI
# from langchain_openai import ChatOpenAI
# from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
# from fastapi.security import OAuth2PasswordBearer
# from pydantic_settings import BaseSettings

load_dotenv()

def evenlabs():
    return ElevenLabs(api_key=os.getenv("EVENLABS"))

# def get_openai_token():
#     return OpenAI(api_key=os.getenv("OPENAI"))

# def get_langchain_token():
#     return ChatOpenAI(model_name="gpt-4o-mini", temperature=0.3, openai_api_key=os.getenv("OPENAI"))

def get_mongodb():
    return AsyncIOMotorClient(os.getenv("MONGO_URI"))
