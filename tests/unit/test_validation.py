import pytest
from pathlib import Path
from github_org_sync.services.validation_service import ValidationService

def test_normalize_org_name_valid() -> None:
    assert ValidationService.normalize_org_name("subactor") == "subactor"
    assert ValidationService.normalize_org_name("https://github.com/subactor") == "subactor"
    assert ValidationService.normalize_org_name("git@github.com:subactor") == "subactor"
    assert ValidationService.normalize_org_name("https://github.com/subactor/") == "subactor"
    assert ValidationService.normalize_org_name(" git@github.com:subactor/ ") == "subactor"

def test_normalize_org_name_invalid() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ValidationService.normalize_org_name("")
        
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("https://github.com/subactor/extra")
        
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("subactor/repo")
        
    with pytest.raises(ValueError, match="Invalid organization name or URL format"):
        ValidationService.normalize_org_name("sub actor")

def test_validate_workspace_valid(tmp_path: Path) -> None:
    # A directory that exists
    validated = ValidationService.validate_workspace(str(tmp_path))
    assert validated.resolve() == tmp_path.resolve()
    
    # A subdirectory of an existing directory (should be valid as parent exists)
    sub = tmp_path / "new_workspace"
    validated_sub = ValidationService.validate_workspace(str(sub))
    assert validated_sub.resolve() == sub.resolve()

def test_validate_workspace_invalid() -> None:
    with pytest.raises(ValueError, match="Workspace path cannot be empty"):
        ValidationService.validate_workspace("")
