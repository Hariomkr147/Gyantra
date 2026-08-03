"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make `app` importable when pytest is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


SAMPLE_CHAPTER = """# Chapter 8: Force and Laws of Motion

## 8.1 Balanced and Unbalanced Forces

A force can be a push or a pull. When several forces act on a body at the same
time, their effects can cancel one another. Such forces are called balanced
forces. If the net force on an object is not zero, the forces are unbalanced and
the object accelerates in the direction of the net force.

Consider a wooden block resting on a table. The weight of the block acts
downwards and the table pushes upwards with an equal force. These two forces are
balanced, so the block stays at rest.

## 8.2 First Law of Motion

An object remains in a state of rest or of uniform motion in a straight line
unless acted upon by an unbalanced external force. This is Newton's first law of
motion, also called the law of inertia.

Inertia is the natural tendency of an object to resist a change in its state of
motion. The mass of an object is a measure of its inertia. A heavier object has
greater inertia than a lighter one.

## 8.3 Second Law of Motion

The rate of change of momentum of an object is proportional to the applied
unbalanced force in the direction of the force.

F = m * a

where F is the force applied, m is the mass of the object, and a is the
acceleration produced. The SI unit of force is the newton (N). One newton is the
force that produces an acceleration of 1 m/s squared in an object of mass 1 kg.

Example 8.1: A force of 5 N acts on a mass of 2 kg. The acceleration produced is
a = F/m = 5/2 = 2.5 m per second squared.

## 8.4 Third Law of Motion

To every action there is an equal and opposite reaction. These forces act on two
different bodies. When a bullet is fired from a gun, the gun recoils backwards
while the bullet moves forward.

| Law | Statement |
| --- | --- |
| First | An object keeps its state unless an unbalanced force acts |
| Second | F equals m times a |
| Third | Action and reaction are equal and opposite |
"""


@pytest.fixture
def sample_text_file(tmp_path: Path) -> Path:
    path = tmp_path / "force_and_motion.md"
    path.write_text(SAMPLE_CHAPTER, encoding="utf-8")
    return path


@pytest.fixture
def sample_chapter_text() -> str:
    return SAMPLE_CHAPTER
