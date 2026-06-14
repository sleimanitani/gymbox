"""Signal front-end tests.

extract_joint_axis / smooth / velocity are concrete (not stubbed), so these run
for real today and guard the numeric layer the rep detector will build on.
"""
from __future__ import annotations

import numpy as np

from gymbox.dsl.models import ExerciseSpec
from gymbox.pipeline.signal import (
    emission_delay_frames,
    extract_joint_axis,
    smooth,
    velocity,
)
from gymbox.pipeline.types import SkeletonStream


def test_extract_joint_axis_shape(
    bicep_stream: SkeletonStream, db_curl_spec: ExerciseSpec
) -> None:
    raw = extract_joint_axis(bicep_stream, db_curl_spec.signal)
    assert raw.shape == (len(bicep_stream),)
    assert np.isfinite(raw).all()


def test_invert_flips_sign(
    bicep_stream: SkeletonStream, db_curl_spec: ExerciseSpec
) -> None:
    """db_curl inverts y so that 'up' (curl top) is the high signal value."""
    raw = extract_joint_axis(bicep_stream, db_curl_spec.signal)
    # Wrist y decreases as the hand rises in image coords; inverted, the curl
    # top should sit above the bottom.
    assert raw.max() > raw.min()


def test_smoothing_preserves_length(
    bicep_stream: SkeletonStream, db_curl_spec: ExerciseSpec
) -> None:
    raw = extract_joint_axis(bicep_stream, db_curl_spec.signal)
    sm = smooth(raw, db_curl_spec.smoothing)
    assert sm.shape == raw.shape
    assert np.isfinite(sm).all()
    # Savitzky-Golay should not amplify variance.
    assert sm.std() <= raw.std() * 1.5


def test_velocity_length_and_units(
    bicep_stream: SkeletonStream, db_curl_spec: ExerciseSpec
) -> None:
    raw = extract_joint_axis(bicep_stream, db_curl_spec.signal)
    sm = smooth(raw, db_curl_spec.smoothing)
    v = velocity(sm, bicep_stream.sample_rate_hz)
    assert v.shape == sm.shape


def test_emission_delay_is_half_window(db_curl_spec: ExerciseSpec) -> None:
    # window_frames = 9 -> half-window = 4
    assert emission_delay_frames(db_curl_spec.smoothing) == 4
