import re
from pathlib import Path

class ValidationService:
    @staticmethod
    def normalize_org_name(org_input: str) -> str:
        """
        Normalize organization input to a clean GitHub organization name.
        Supported formats:
        - name
        - https://github.com/name
        - git@github.com:name
        - and potential variations with trailing slashes/spaces.
        """
        if not org_input:
            raise ValueError("Organization name or URL cannot be empty")
            
        cleaned = org_input.strip()
        
        # Match git@github.com:orgname or git@github.com:orgname/
        ssh_match = re.match(r"^git@github\.com:([^/]+)(?:/)?$", cleaned)
        if ssh_match:
            return ssh_match.group(1)
            
        # Match http(s)://(www.)github.com/orgname or http(s)://(www.)github.com/orgname/
        http_match = re.match(r"^https?://(?:www\.)?github\.com/([^/]+)(?:/)?$", cleaned)
        if http_match:
            return http_match.group(1)
            
        # Simple name check: should not contain slashes, spaces, or colons
        if "/" in cleaned or "\\" in cleaned or ":" in cleaned or " " in cleaned:
            raise ValueError(f"Invalid organization name or URL format: {org_input}")
            
        return cleaned

    @staticmethod
    def validate_workspace(path_str: str) -> Path:
        """
        Validates that workspace directory is a valid local path.
        """
        if not path_str:
            raise ValueError("Workspace path cannot be empty")
            
        path = Path(path_str).resolve()
        
        # Check if parent directory exists (or if it exists)
        if not path.exists():
            try:
                # Test creation of directory or check parent directory
                parent = path.parent
                if not parent.exists():
                    raise ValueError(f"Parent directory does not exist: {parent}")
            except Exception as e:
                raise ValueError(f"Invalid workspace path: {e}") from e
                
        return path
