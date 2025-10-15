from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "name": "All-in-One-DeFi-Bot"}
