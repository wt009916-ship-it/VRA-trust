"""Revocable project-scoped API credentials; raw secrets are returned exactly once."""
import json
import secrets
import time
from typing import Literal

from pydantic import Field

from .auth import digest
from .domain import identifier
from .schema import Contract


class TokenCreate(Contract):
    name: str = Field(min_length=1, max_length=80)
    days: int = Field(default=30, ge=1, le=90)
    scopes: list[Literal["read", "write", "compute"]] = Field(default=["read"], min_length=1, max_length=3)


class Tokens:
    def __init__(self, auth):
        self.auth, self.store = auth, auth.store
        with self.store.connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS api_tokens
                (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
                 project_id TEXT NOT NULL, name TEXT NOT NULL, scopes TEXT NOT NULL,
                 expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)""")

    def create(self, project_id, user_id, body):
        self.auth.require_project(project_id, user_id)
        token = "vra_" + secrets.token_urlsafe(40)
        row = {"id": identifier("token"), "project_id": project_id, "name": body.name,
               "scopes": sorted(set(body.scopes)), "expires": time.time()+body.days*86400}
        with self.store.connect() as con:
            con.execute("INSERT INTO api_tokens VALUES (?,?,?,?,?,?,?,0)",
                        (row["id"], digest(token), user_id, project_id, row["name"], json.dumps(row["scopes"]), row["expires"]))
        return {**row, "token": token}

    def list(self, project_id, user_id):
        with self.store.connect() as con:
            return [{**dict(row), "scopes": json.loads(row["scopes"])} for row in con.execute(
                "SELECT id,project_id,name,scopes,expires,revoked FROM api_tokens WHERE project_id=? AND user_id=?",
                (project_id, user_id))]

    def revoke(self, project_id, user_id, token_id):
        with self.store.connect() as con:
            con.execute("UPDATE api_tokens SET revoked=1 WHERE id=? AND project_id=? AND user_id=?",
                        (token_id, project_id, user_id))
        return {"revoked": True}

    def authenticate(self, token):
        if len(token) > 200:
            return None
        with self.store.connect() as con:
            row = con.execute("""SELECT t.*,u.username,u.display_name FROM api_tokens t
                JOIN users u ON u.id=t.user_id WHERE token_hash=? AND revoked=0 AND expires>? AND u.disabled=0""",
                (digest(token), time.time())).fetchone()
        if not row or not self.auth.allows(row["project_id"], row["user_id"]):
            return None
        return {"id": row["user_id"], "username": row["username"], "display_name": row["display_name"],
                "csrf": "", "is_admin": False, "api_project": row["project_id"],
                "scopes": json.loads(row["scopes"])}

    def permits(self, user, method, path):
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[1] == "projects" and parts[2] == user["api_project"]:
            if "tokens" in parts:
                return False
            scope = "read" if method in {"GET", "HEAD"} else "write"
            if method not in {"GET", "HEAD"} and any(p in parts for p in {"model-runs", "agent", "searches", "studies"}):
                # External clients use the narrow simulation API; arbitrary agent mutation is unavailable.
                return parts[-1] == "model-runs" and "compute" in user["scopes"]
            return scope in user["scopes"]
        if len(parts) >= 3 and parts[1] == "runs" and method in {"GET", "HEAD"}:
            try:
                return self.store.job(parts[2])["project_id"] == user["api_project"] and "read" in user["scopes"]
            except (KeyError, ValueError):
                return False
        return False
