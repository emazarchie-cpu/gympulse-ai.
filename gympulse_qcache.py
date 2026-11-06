"""GymPulse AI · A short-lived read cache in front of the Supabase client.

The member app reruns its whole page on every tap. Without a cache that meant ~35 database
round trips per tap (about 3–4 seconds from Render to Supabase). This wrapper remembers
the result of each read (select) for a few seconds, per browser session. Any write
(insert / update / upsert / delete) to a table clears that table's cached reads at once,
so members always see their own changes immediately; other people's changes appear within
the table's few seconds.

    sc = CachedClient(service_client())
    sc.table("community_posts").select("*").eq("gym_id", g).execute()   # cached
"""
import time

import streamlit as st

TTL = {"community_dms": 4, "community_notifications": 6, "checkins": 30, "messages": 8}
DEFAULT_TTL = 20
_WRITES = ("insert", "update", "upsert", "delete")


def _store():
    s = st.session_state.get("_qcache")
    if not isinstance(s, dict):
        s = {}
        st.session_state["_qcache"] = s
    return s


def clear(table=None):
    s = _store()
    for k in [k for k in s if table is None or k[0] == table]:
        s.pop(k, None)


class _Res:
    def __init__(self, data):
        self.data = data


class _Chain:
    def __init__(self, client, name):
        self._client, self._name, self._calls = client, name, []

    def __getattr__(self, method):
        def call(*a, **k):
            self._calls.append((method, a, k))
            return self
        return call

    def execute(self):
        op = next((m for m, _, _ in self._calls if m in ("select",) + _WRITES), "select")
        q = self._client.table(self._name)
        if op != "select":
            for m, a, k in self._calls:
                q = getattr(q, m)(*a, **k)
            res = q.execute()
            clear(self._name)
            return res
        key = (self._name, repr(self._calls))
        s = _store()
        hit = s.get(key)
        now = time.time()
        if hit and now - hit[0] < TTL.get(self._name, DEFAULT_TTL):
            return _Res(_copy(hit[1]))
        for m, a, k in self._calls:
            q = getattr(q, m)(*a, **k)
        res = q.execute()
        data = getattr(res, "data", None)
        s[key] = (now, _copy(data))
        if len(s) > 600:                          # keep it small: drop the oldest half
            for k in sorted(s, key=lambda x: s[x][0])[:300]:
                s.pop(k, None)
        return res


def _copy(data):
    if isinstance(data, list):
        return [dict(x) if isinstance(x, dict) else x for x in data]
    return dict(data) if isinstance(data, dict) else data


class CachedClient:
    """Wraps a Supabase client: table() reads are cached briefly; everything else passes straight through."""

    def __init__(self, client):
        self._client = client

    def table(self, name):
        return _Chain(self._client, name)

    def rpc(self, *a, **k):
        clear()                                    # functions may write anything
        return self._client.rpc(*a, **k)

    def __getattr__(self, name):
        return getattr(self._client, name)
