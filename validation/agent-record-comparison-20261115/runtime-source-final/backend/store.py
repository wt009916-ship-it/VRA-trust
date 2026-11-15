"""Append-only entity revisions; private files and job metadata persist locally."""
import json
import re
import sqlite3
from pathlib import Path

from . import core
from .task_capacity import TaskLimits, CapacityError


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "vra.sqlite3"
        self.task_limits = TaskLimits.from_env()
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL,
                    project_id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(kind,id,revision));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL,
                    body TEXT NOT NULL, error TEXT);
            """)

    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def check_id(identifier):
        if not re.fullmatch(r"[a-z]+_[a-f0-9]{32}", identifier):
            raise core.ValidationError("Invalid identifier")
        return identifier

    def put(self, kind, obj, expected=0):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            return self.put_in(con, kind, obj, expected)

    def put_in(self, con, kind, obj, expected=0):
        """Append within the caller's existing transaction; never commit here."""
        key = obj[kind + "_id"]
        self.check_id(key)
        if not con.in_transaction:
            raise RuntimeError('put_in requires an explicit write transaction')
        row = con.execute("SELECT MAX(revision) FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        if (row[0] or 0) != expected:
            raise core.ValidationError("Revision conflict; refresh before editing")
        obj = {**obj, "revision": expected + 1}
        con.execute("INSERT INTO records VALUES (?,?,?,?,?)", (kind, key, expected + 1, obj.get("project_id", key), json.dumps(obj, ensure_ascii=False, allow_nan=False)))
        return obj

    def get(self, kind, key, revision=None):
        self.check_id(key)
        with self.connect() as con:
            if revision is None:
                row = con.execute("SELECT body FROM records WHERE kind=? AND id=? ORDER BY revision DESC LIMIT 1", (kind, key)).fetchone()
            else:
                row = con.execute("SELECT body FROM records WHERE kind=? AND id=? AND revision=?", (kind, key, revision)).fetchone()
        if row is None:
            raise KeyError(key)
        return json.loads(row[0])

    def list(self, kind, project_id=None):
        with self.connect() as con:
            query = "SELECT body FROM records r WHERE kind=? AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)"
            args = [kind]
            if project_id:
                query += " AND project_id=?"
                args.append(project_id)
            rows = con.execute(query + " ORDER BY rowid DESC", args).fetchall()
        return [json.loads(r[0]) for r in rows]

    def history(self, kind, key):
        self.check_id(key)
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute("SELECT body FROM records WHERE kind=? AND id=? ORDER BY revision", (kind, key))]

    def add_job(self, job):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            total,project=con.execute("SELECT COUNT(*),COALESCE(SUM(project_id=?),0) FROM jobs WHERE state IN ('queued','running')",(job['project_id'],)).fetchone()
            if total>=self.task_limits.runs or project>=self.task_limits.project_runs:
                raise CapacityError('仿真待执行/运行任务已达容量上限，请等待或取消排队任务')
            con.execute("INSERT INTO jobs VALUES (?,?,?,?,NULL)", (job["run_id"], job["project_id"], "queued", json.dumps(job, ensure_ascii=False, allow_nan=False)))

    def add_active_record(self, kind, record):
        if kind not in {'agent','search'}:raise ValueError('Unsupported task kind')
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            rows=con.execute("SELECT body FROM records r WHERE kind=? AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)",(kind,))
            active=sum(json.loads(row[0]).get('status')=='running' for row in rows)
            if active>=getattr(self.task_limits,kind):raise CapacityError('本机任务容量已满；未新增任务')
            return self.put_in(con,kind,record)

    def cancel_job(self, run_id):
        self.check_id(run_id)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT state FROM jobs WHERE id=?',(run_id,)).fetchone()
            if row is None:raise KeyError(run_id)
            if row[0]=='queued':con.execute("UPDATE jobs SET state='failed',error='Cancelled before execution' WHERE id=?",(run_id,))
            elif row[0]=='running':con.execute("UPDATE jobs SET error='CANCEL_REQUESTED' WHERE id=?",(run_id,))

    def cancel_requested(self, run_id):
        with self.connect() as con:
            row=con.execute('SELECT error FROM jobs WHERE id=?',(run_id,)).fetchone()
            return bool(row and row[0]=='CANCEL_REQUESTED')

    def job(self, run_id):
        self.check_id(run_id)
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return {**json.loads(row["body"]), "status": row["state"], "error": row["error"]}

    def jobs(self, project_id):
        with self.connect() as con:
            return [self.job(r[0]) for r in con.execute("SELECT id FROM jobs WHERE project_id=? ORDER BY rowid DESC", (project_id,))]

    def claim_job(self):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
            if row:
                con.execute("UPDATE jobs SET state='running' WHERE id=?", (row[0],))
        return self.job(row[0]) if row else None

    def finish(self, run_id, state, error=None):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            previous=con.execute('SELECT error FROM jobs WHERE id=?',(run_id,)).fetchone()
            if previous and previous[0]=='CANCEL_REQUESTED':state,error='failed','Cancelled; execution terminated or result discarded'
            con.execute("UPDATE jobs SET state=?,error=? WHERE id=?", (state, error, run_id))

    def recover(self):
        with self.connect() as con:
            con.execute("UPDATE jobs SET state='failed',error='Worker interrupted; create a new run' WHERE state='running'")
