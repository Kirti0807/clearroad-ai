"""
Database layer for ClearRoad AI.

Uses psycopg2 against CockroachDB (which speaks the PostgreSQL wire
protocol, so standard psycopg2 works against it directly). Works equally
against plain PostgreSQL if you'd rather run that locally instead.

All functions are defensive about connection failures -- if the DB is
unreachable, the app should keep running in "live view only" mode rather
than crashing, since the core hazard-detection/alerting loop shouldn't
depend on the database being up.
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

import config

# Connection string can be overridden via env var for flexibility between
# local Docker Compose, CockroachDB Cloud, etc. This default matches the
# docker-compose.yml service in this project.
# Uses CockroachDB's built-in "defaultdb" rather than a custom database
# name -- avoids needing a separate database-creation step before the app
# can connect. Fine to point this at a dedicated database instead once
# you're past initial setup.
DATABASE_URL = os.environ.get(
    "CLEARROAD_DB_URL",
    "postgresql://root@localhost:26257/defaultdb?sslmode=disable",
)


@contextmanager
def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_schema():
    """
    Creates tables if they don't exist yet. Safe to call every time the
    app starts -- CREATE TABLE IF NOT EXISTS is idempotent.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS visibility_metrics (
                    id SERIAL PRIMARY KEY,
                    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    visibility_score FLOAT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS hazard_logs (
                    id SERIAL PRIMARY KEY,
                    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    class_name TEXT NOT NULL,
                    confidence FLOAT NOT NULL,
                    box_height_ratio FLOAT NOT NULL,
                    visibility_score FLOAT
                );
                """
            )
            conn.commit()


def log_visibility(score: float):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO visibility_metrics (visibility_score) VALUES (%s);",
                    (score,),
                )
                conn.commit()
    except psycopg2.Error:
        # DB write failures shouldn't take down the live detection loop.
        pass


def log_hazards(detections: list, visibility_score: float):
    if not detections:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO hazard_logs
                        (class_name, confidence, box_height_ratio, visibility_score)
                    VALUES (%s, %s, %s, %s);
                    """,
                    [
                        (d.class_name, d.confidence, d.box_height_ratio, visibility_score)
                        for d in detections
                    ],
                )
                conn.commit()
    except psycopg2.Error:
        pass


def fetch_recent_hazards(limit: int = 25):
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT detected_at, class_name, confidence, box_height_ratio, visibility_score
                    FROM hazard_logs
                    ORDER BY detected_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                return cur.fetchall()
    except psycopg2.Error:
        return []


def fetch_daily_hazard_counts(days: int = 7):
    """Returns [(date, count), ...] for the last N days, oldest first."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT date_trunc('day', detected_at)::date AS day, COUNT(*)
                    FROM hazard_logs
                    WHERE detected_at >= now() - (%s || ' days')::interval
                    GROUP BY day
                    ORDER BY day ASC;
                    """,
                    (days,),
                )
                return cur.fetchall()
    except psycopg2.Error:
        return []


def fetch_visibility_trend(limit: int = 50):
    """Returns most recent visibility scores, oldest first, for charting."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT recorded_at, visibility_score
                    FROM (
                        SELECT recorded_at, visibility_score
                        FROM visibility_metrics
                        ORDER BY recorded_at DESC
                        LIMIT %s
                    ) sub
                    ORDER BY recorded_at ASC;
                    """,
                    (limit,),
                )
                return cur.fetchall()
    except psycopg2.Error:
        return []


def fetch_users():
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id;")
                return cur.fetchall()
    except psycopg2.Error:
        return []


def add_user(username: str, role: str = "viewer"):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, role) VALUES (%s, %s) "
                    "ON CONFLICT (username) DO NOTHING;",
                    (username, role),
                )
                conn.commit()
        return True
    except psycopg2.Error:
        return False
