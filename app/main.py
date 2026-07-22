from fastapi import FastAPI

app = FastAPI(title="Interview Scorecard")

@app.get("/healthz")
def healthz():
    return {"ok": True}
