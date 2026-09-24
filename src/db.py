"""Shared PostgreSQL connection helper for the analytics scripts."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    load_dotenv()
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "neobank_analytics"),
        user=os.getenv("POSTGRES_USER", "neobank_user"),
        password=os.getenv("POSTGRES_PASSWORD", "change_me_local_only"),
    )
