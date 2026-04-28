import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DB_PATH = os.getenv("RESULTS_DB_PATH", "results.db")
API_KEY = os.getenv("RESULTS_API_KEY", "").strip()


class ResultIn(BaseModel):
    user: str = Field(min_length=1)
    lesson: str = Field(default="1")
    type: str = Field(default="logic_quiz")
    points: int = 0
    stars: int = 0
    correct: str = Field(default="incorrect")
    duration: int = 0
    answer: str = ""
    expected: str = ""
    source: str = "telegram_bot"
    time: Optional[str] = None


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                lesson TEXT NOT NULL,
                type TEXT NOT NULL,
                points INTEGER NOT NULL DEFAULT 0,
                stars INTEGER NOT NULL DEFAULT 0,
                correct TEXT NOT NULL DEFAULT 'incorrect',
                duration INTEGER NOT NULL DEFAULT 0,
                answer TEXT NOT NULL DEFAULT '',
                expected TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'telegram_bot',
                created_at TEXT NOT NULL
            )
            """
        )


def serialize_row(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "user": row["user"],
        "lesson": row["lesson"],
        "type": row["type"],
        "points": row["points"],
        "stars": row["stars"],
        "correct": row["correct"],
        "duration": row["duration"],
        "answer": row["answer"],
        "expected": row["expected"],
        "source": row["source"],
        "time": row["created_at"],
    }


def verify_api_key(x_api_key: Optional[str]) -> None:
    if not API_KEY:
        return
    if not x_api_key or x_api_key.strip() != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


app = FastAPI(title="NeoLingo Results API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/results")
def list_results(limit: int = 500) -> List[Dict[str, Any]]:
    limit = max(1, min(5000, limit))
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM results ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [serialize_row(r) for r in rows]


@app.post("/api/results")
def create_result(payload: ResultIn, x_api_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    verify_api_key(x_api_key)
    created_at = payload.time or datetime.now(timezone.utc).isoformat()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO results (user, lesson, type, points, stars, correct, duration, answer, expected, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.user.strip(),
                payload.lesson.strip(),
                payload.type.strip(),
                int(payload.points),
                int(payload.stars),
                payload.correct.strip(),
                int(payload.duration),
                payload.answer.strip(),
                payload.expected.strip(),
                payload.source.strip(),
                created_at,
            ),
        )
        row_id = cur.lastrowid
        row = conn.execute("SELECT * FROM results WHERE id = ?", (row_id,)).fetchone()
    return serialize_row(row)
