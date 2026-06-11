import firebase_admin
from firebase_admin import credentials, auth
import os
from dotenv import load_dotenv
from fastapi import HTTPException, Header
from typing import Optional
import glob

load_dotenv()

def init_firebase():
    if not firebase_admin._apps:
        # Search for JSON file in current directory and common locations
        json_files = glob.glob("*.json") + glob.glob("**/*.json", recursive=False)
        # Filter to firebase service account files
        sa_files = [f for f in json_files if 'firebase' in f.lower() or 'adminsdk' in f.lower()]
        
        if sa_files:
            json_path = sa_files[0]
            print(f"Found Firebase JSON: {json_path}")
            cred = credentials.Certificate(json_path)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized successfully!")
        else:
            # Try env variables as fallback
            private_key = os.getenv("FIREBASE_PRIVATE_KEY", "")
            if private_key and "BEGIN" in private_key:
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
                    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
                    "private_key": private_key.replace("\\n", "\n"),
                    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
                    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                })
                firebase_admin.initialize_app(cred)
                print("Firebase initialized from env variables!")
            else:
                print("ERROR: No Firebase credentials found!")
                print("Put your firebase service account JSON in:", os.getcwd())
                raise Exception("Firebase credentials not found. Add the JSON file to the backend folder.")

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
