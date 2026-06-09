"""Materializer (architecture.md §5, §9).

Background job that denormalizes the polymorphic `annotations` rows into the
fast-query `sets` / `reps` tables. Runs every few minutes; not real-time.

The derivation is concrete because the annotation layers are locked: `set`,
`rep`, and `rep_phase` spans fully determine the materialized rows. Each rep's
`phase_durations_s` is summed from the rep_phase annotations falling within the
rep span; amplitude is read from the rep annotation's metadata if present.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .persistence import Annotation, Rep, Session, Set


async def materialize_pending(session: AsyncSession) -> int:
    """Materialize all sessions flagged `materialized=False`. Returns count."""
    res = await session.execute(select(Session).where(Session.materialized.is_(False)))
    pending = list(res.scalars().all())
    for s in pending:
        await materialize_session(session, s)
        s.materialized = True
    return len(pending)


async def materialize_session(session: AsyncSession, sess: Session) -> None:
    """Rebuild sets/reps for one session from its annotations."""
    # Clear prior materialization (idempotent re-run on update).
    await session.execute(delete(Rep).where(Rep.session_id == sess.id))
    await session.execute(delete(Set).where(Set.session_id == sess.id))
    await session.flush()

    anns_res = await session.execute(
        select(Annotation)
        .where(Annotation.session_id == sess.id)
        .order_by(Annotation.start_s)
    )
    anns = list(anns_res.scalars().all())

    set_anns = [a for a in anns if a.layer_id == "set"]
    rep_anns = [a for a in anns if a.layer_id == "rep"]
    phase_anns = [a for a in anns if a.layer_id == "rep_phase"]
    side_anns = [a for a in anns if a.layer_id == "movement_side"]

    # If no explicit set annotations exist, synthesize a single set spanning the
    # session (MVP-α single-set sessions are common).
    if not set_anns:
        synthetic_span = _session_span(rep_anns, sess)
        set_rows = [
            Set(
                session_id=sess.id,
                index_in_session=0,
                start_s=synthetic_span[0],
                end_s=synthetic_span[1],
                rep_count=0,
                movement_side=_side_for(synthetic_span, side_anns),
                weight_kg=sess.weight_kg,
            )
        ]
    else:
        set_rows = [
            Set(
                session_id=sess.id,
                index_in_session=i,
                start_s=a.start_s,
                end_s=a.end_s,
                rep_count=0,
                movement_side=_side_for((a.start_s, a.end_s), side_anns),
                weight_kg=sess.weight_kg,
            )
            for i, a in enumerate(set_anns)
        ]

    for s in set_rows:
        session.add(s)
    await session.flush()

    # Assign reps to sets by temporal containment.
    for rep_idx_global, rep in enumerate(sorted(rep_anns, key=lambda a: a.start_s)):
        owning_set = _containing_set(rep, set_rows)
        index_in_set = sum(
            1
            for r in rep_anns
            if r.start_s < rep.start_s and _containing_set(r, set_rows) is owning_set
        )
        durations = _phase_durations(rep, phase_anns)
        amplitude = None
        if rep.annotation_metadata and "amplitude" in rep.annotation_metadata:
            amplitude = float(rep.annotation_metadata["amplitude"])
        session.add(
            Rep(
                session_id=sess.id,
                set_id=owning_set.id if owning_set else None,
                index_in_set=index_in_set,
                start_s=rep.start_s,
                end_s=rep.end_s,
                amplitude=amplitude,
                phase_durations_s=durations or None,
            )
        )
        if owning_set is not None:
            owning_set.rep_count += 1

    await session.flush()


def _session_span(rep_anns: list[Annotation], sess: Session) -> tuple[float, float]:
    if rep_anns:
        return (min(a.start_s for a in rep_anns), max(a.end_s for a in rep_anns))
    return (0.0, max(0.0, (sess.ended_at - sess.started_at).total_seconds()))


def _containing_set(rep: Annotation, sets: list[Set]) -> Set | None:
    mid = (rep.start_s + rep.end_s) / 2
    for s in sets:
        if s.start_s <= mid <= s.end_s:
            return s
    return sets[0] if sets else None


def _phase_durations(rep: Annotation, phase_anns: list[Annotation]) -> dict[str, float]:
    """Sum rep_phase durations overlapping the rep span, keyed by phase value."""
    out: dict[str, float] = {}
    for p in phase_anns:
        overlap = min(p.end_s, rep.end_s) - max(p.start_s, rep.start_s)
        if overlap > 0:
            out[p.value] = round(out.get(p.value, 0.0) + overlap, 4)
    return out


def _side_for(span: tuple[float, float], side_anns: list[Annotation]) -> str | None:
    mid = (span[0] + span[1]) / 2
    for s in side_anns:
        if s.start_s <= mid <= s.end_s:
            return s.value
    return side_anns[0].value if side_anns else None
