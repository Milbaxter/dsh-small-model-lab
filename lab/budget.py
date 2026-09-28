"""Transactional controller-owned run budgets; task containers never mount this DB."""
from contextlib import contextmanager
import hashlib
import json
import math
import secrets
import sqlite3
import time


class BudgetExceeded(ValueError):
    pass


class Ledger:
    def __init__(self, path, total_usd=30.0):
        if not math.isfinite(total_usd) or total_usd <= 0:
            raise ValueError("Global budget must be finite and positive")
        self.path = str(path)
        with self.transaction() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, deadline REAL NOT NULL,
                max_requests INTEGER NOT NULL, max_tokens INTEGER NOT NULL,
                requests INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0,
                reserved_tokens INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'active', config TEXT NOT NULL DEFAULT '{}');
              CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, max_tokens INTEGER NOT NULL,
                reserved_usd REAL NOT NULL, cost_usd REAL, used_tokens INTEGER,
                status TEXT NOT NULL DEFAULT 'reserved');
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?, ?)', ('total_usd', total_usd))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            if db.in_transaction:
                db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def register(self, run_id, *, max_requests, max_tokens, wall_seconds, config=None):
        if min(max_requests, max_tokens, wall_seconds) <= 0:
            raise ValueError('Budgets must be positive')
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute('INSERT INTO runs(id, token_hash, deadline, max_requests, max_tokens, config) VALUES (?,?,?,?,?,?)',
                       (run_id, self.digest(token), time.time() + wall_seconds, max_requests, max_tokens, json.dumps(config or {})))
        return token

    def configuration(self, token):
        with self.transaction() as db:
            row = db.execute('SELECT config FROM runs WHERE token_hash=?', (self.digest(token),)).fetchone()
            if row is None:
                raise BudgetExceeded('Unknown run token')
            return json.loads(row[0])

    def reserve(self, token, *, max_tokens, worst_cost_usd):
        if max_tokens <= 0 or not math.isfinite(worst_cost_usd) or worst_cost_usd <= 0:
            raise ValueError('Reservation must be positive')
        with self.transaction() as db:
            row = db.execute('SELECT id, deadline, max_requests, max_tokens, requests, tokens, reserved_tokens, status FROM runs WHERE token_hash=?', (self.digest(token),)).fetchone()
            if row is None:
                raise BudgetExceeded('Unknown run token')
            run_id, deadline, requests_limit, token_limit, requests, tokens, reserved, status = row
            if status != 'active' or time.time() >= deadline:
                raise BudgetExceeded('Run closed or expired')
            if requests >= requests_limit or tokens + reserved + max_tokens > token_limit:
                raise BudgetExceeded('Run request or token budget exhausted')
            spent = db.execute('SELECT COALESCE(SUM(COALESCE(cost_usd, reserved_usd)),0) FROM requests').fetchone()[0]
            limit = db.execute('SELECT value FROM settings WHERE name=?', ('total_usd',)).fetchone()[0]
            if spent + worst_cost_usd > limit:
                raise BudgetExceeded('Global cost budget exhausted')
            request_id = secrets.token_hex(16)
            db.execute('INSERT INTO requests(id,run_id,max_tokens,reserved_usd) VALUES (?,?,?,?)', (request_id, run_id, max_tokens, worst_cost_usd))
            db.execute('UPDATE runs SET requests=requests+1, reserved_tokens=reserved_tokens+? WHERE id=?', (max_tokens, run_id))
        return request_id, run_id

    def settle(self, request_id, *, used_tokens, cost_usd):
        if used_tokens < 0 or not math.isfinite(cost_usd) or cost_usd < 0:
            raise ValueError('Usage must be nonnegative')
        with self.transaction() as db:
            row = db.execute('SELECT run_id,max_tokens,status FROM requests WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown reservation')
            run_id, reserved, status = row
            if status != 'reserved':
                raise ValueError('Reservation already settled')
            # Retain actual overshoots in the ledger; they close subsequent admissions.
            db.execute('UPDATE requests SET used_tokens=?,cost_usd=?,status=? WHERE id=?', (used_tokens,cost_usd,'settled',request_id))
            db.execute('UPDATE runs SET tokens=tokens+?,reserved_tokens=reserved_tokens-? WHERE id=?', (used_tokens,reserved,run_id))

    def close(self, run_id):
        with self.transaction() as db:
            db.execute("UPDATE runs SET status='closed' WHERE id=?", (run_id,))
