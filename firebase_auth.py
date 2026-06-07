import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
from fastapi import HTTPException, Header
from typing import Optional

load_dotenv()

def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.getenv("FIREBASE_PROJECT_ID"),
            "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
            "client_id": os.getenv("FIREBASE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        firebase_admin.initialize_app(cred)

def verify_token(token: str) -> dict:
    """Verify Firebase ID token and return decoded claims"""
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def create_firebase_user(email: str, password: str) -> str:
    """Create user in Firebase Auth, return UID"""
    try:
        user = auth.create_user(email=email, password=password)
        return user.uid
    except auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def delete_firebase_user(uid: str):
    """Delete user from Firebase Auth"""
    try:
        auth.delete_user(uid)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency — extracts and verifies token from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token provided")
    token = authorization.split("Bearer ")[1]
    return verify_token(token)
