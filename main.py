# main.py
import os
import shutil
import requests
from tempfile import NamedTemporaryFile
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Depends, Cookie
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from urllib.parse import urlencode
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from rag import setup_milvus, ingest_pdf, Chatbot

# Load environment variables
load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

user_sessions = {} 

# Setup RAG
collection = setup_milvus()
chatbot = Chatbot(collection)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ---------- Google OAuth ----------
@app.get("/auth/login")
def login():
    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    return RedirectResponse(f"{google_auth_url}?{urlencode(params)}")

@app.get("/auth/google/callback")
def callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    token_res = requests.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    })

    token_json = token_res.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    user_info = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Failed to fetch user email")

    user_sessions[access_token] = {
        "email": email,
        "file_name": None # Store file name for context retrieval
    }
    response = RedirectResponse(url="/")

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True
    )
    return response

# ---------- Dependency ----------
def get_current_user(access_token: str = Cookie(None)):
    user_data = user_sessions.get(access_token)
    if not user_data:
        raise HTTPException(status_code=401, detail="Not logged in or session expired")
    return user_data

# ---------- Upload ----------
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files allowed.")
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    try:
        ingest_pdf(temp_path, collection, file.filename)
        user["file_name"] = file.filename
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.remove(temp_path)

# ---------- Chat ----------
class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat_with_pdf(request: ChatRequest, user: dict = Depends(get_current_user)):
    file_name = user.get("file_name")
    if not file_name:
        raise HTTPException(status_code=400, detail="No file uploaded yet.")
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Empty message")
    response = chatbot.chat(request.message, file_name)
    return {"response": response}
