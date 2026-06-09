"""gymbox reference pipeline (architecture.md §5).

These are **reference** implementations: the golden oracle for validating the
Swift port (Gate B), batch replay of uploaded sessions during tuning, and a
labeling assistant. They are NOT on the runtime critical path — the phone runs
the Swift DSL interpreter; this is the Python mirror.

`rep.py` is ROADMAP Step 3 and the FIRST MVP-α milestone. Its acceptance bar
(Gate A) is rep-count error ≤1 and frame-level phase agreement ≥85% against the
human-labelled bicep_curl_1 fixture.
"""
