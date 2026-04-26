import pytest

from .qdrant_store import _validate_vectors


def test_validate_vectors_rejects_empty_vector() -> None:
    with pytest.raises(ValueError, match="empty vector"):
        _validate_vectors([[0.1, 0.2], []])


def test_validate_vectors_rejects_mixed_dimensions() -> None:
    with pytest.raises(ValueError, match="dimension mismatch"):
        _validate_vectors([[0.1, 0.2], [0.3]])
