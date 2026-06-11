import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
from fastapi import HTTPException, Header
from typing import Optional

load_dotenv()

def init_firebase():
    if not firebase_admin._apps:
        json_file = "dr-kcc-academy-app-firebase-adminsdk-fbsvc-46d6afe9e1.json"
        if os.path.exists(json_file):
            cred = credentials.Certificate(json_file)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized with service account JSON")
        else:
            firebase_admin.initialize_app(options={"projectId": "dr-kcc-academy-app"})
            print("Firebase in DEV MODE - no JSON found")

def verify_token(token: str) -> dict:
    try:
        return auth.verify_id_token(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def create_firebase_user(email: str, password: str) -> str:
    try:
        user = auth.create_user(email=email, password=password)
        return user.uid
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def delete_firebase_user(uid: str):
    try:
        auth.delete_user(uid)
    except Exception:
        pass

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")
    token = authorization.split("Bearer ")[1]
    return verify_token(token)