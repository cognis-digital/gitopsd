"""gitopsd — GitOps drift detection. Part of the Cognis Neural Suite."""

from gitopsd.core import (
    TOOL_NAME,
    TOOL_VERSION,
    GitopsError,
    detect_drift,
    diff_resource,
    explain_drift,
    load_state_dir,
    parse_manifests,
    resource_key,
    to_json_patch,
)

__version__ = TOOL_VERSION

__all__ = [
    "TOOL_NAME", "TOOL_VERSION", "__version__", "GitopsError",
    "detect_drift", "diff_resource", "explain_drift", "load_state_dir",
    "parse_manifests", "resource_key", "to_json_patch",
]
