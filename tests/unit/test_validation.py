from pathlib import Path

import pytest

from github_org_sync.services.validation_service import ValidationService


@pytest.mark.unit
def test_normalize_org_name_valid() -> None:
    assert ValidationService.normalize_org_name("subactor") == "subactor"
    assert ValidationService.normalize_org_name("https://github.com/subactor") == "subactor"
    assert ValidationService.normalize_org_name("git@github.com:subactor") == "subactor"
    assert ValidationService.normalize_org_name("https://github.com/subactor/") == "subactor"
    assert ValidationService.normalize_org_name(" git@github.com:subactor/ ") == "subactor"
    assert ValidationService.normalize_org_name("org-with-hyphens") == "org-with-hyphens"


@pytest.mark.unit
def test_normalize_org_name_invalid() -> None:
    # Empty
    with pytest.raises(ValueError, match="cannot be empty"):
        ValidationService.normalize_org_name("")

    with pytest.raises(ValueError, match="cannot be empty"):
        ValidationService.normalize_org_name("   ")

    # Invalid URL formatting / subpages / repo instead of org
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("https://github.com/subactor/repo")

    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("subactor/repo")

    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("sub actor")

    # Disallowed characters
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("sub:actor")

    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("sub\\actor")

    # Invalid domains
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("https://gitlab.com/subactor")

    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("git@gitlab.com:subactor")

    # Very long inputs / path traversal attempts
    with pytest.raises(ValueError, match="cannot exceed 39 characters"):
        ValidationService.normalize_org_name("A" * 100)  # GitHub limit is 39 characters

    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("../subactor")


@pytest.mark.unit
def test_validate_workspace_valid(tmp_path: Path) -> None:
    validated = ValidationService.validate_workspace(str(tmp_path))
    assert validated.resolve() == tmp_path.resolve()

    sub = tmp_path / "new_workspace"
    validated_sub = ValidationService.validate_workspace(str(sub))
    assert validated_sub.resolve() == sub.resolve()


@pytest.mark.unit
def test_validate_workspace_invalid(tmp_path: Path) -> None:
    # Empty
    with pytest.raises(ValueError, match="Workspace path cannot be empty"):
        ValidationService.validate_workspace("")

    # Parent directory does not exist
    non_existent_parent = tmp_path / "non_existent_dir" / "workspace"
    with pytest.raises(ValueError, match="Parent directory does not exist"):
        ValidationService.validate_workspace(str(non_existent_parent))

    # Path traversal with invalid parent
    traversal = tmp_path / ".." / ".." / "non_existent_parent" / "traversal"
    with pytest.raises(ValueError, match="Parent directory does not exist"):
        ValidationService.validate_workspace(str(traversal))
