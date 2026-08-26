"""
tests/computer/test_target_resolver.py
WHAT THIS IS FOR: Test target resolution chain.
"""
from __future__ import annotations
from friday.computer.target_resolver import TargetResolver, ResolutionMethod

def test_resolve():
    resolver = TargetResolver()
    result = resolver.resolve("Submit button")
    assert result is not None
    assert result.method == ResolutionMethod.ACCESSIBILITY_LABEL
    assert result.confidence > 0
