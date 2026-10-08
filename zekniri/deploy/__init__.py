"""Deploy subpackage — atomic swap, manifest parsing, template render, assets,
and the deploy orchestrator.

Re-exports keep external imports shallow. For test patching, address the
defining submodule directly (e.g. ``zekniri.deploy.atomic.atomic_replace_item``).
"""

from zekniri.deploy.atomic import atomic_replace_item
from zekniri.deploy.manifest import (
    ModuleManifest,
    load_manifest,
    load_manifest_for,
    discover_manifest_apps,
    discover_deployable_apps,
    discover_optional_apps,
    load_optional_apps,
)
from zekniri.deploy.templates import _phase_render_templates
from zekniri.deploy.assets import (
    AssetDeployResult,
    assets_present,
    deploy_assets,
)
from zekniri.deploy.deploy import (
    discover_config_items,
    _phase_atomic_deployment,
    deploy_selected_configs,
    deploy_runtime_conf,
    render_completion_screen,
    test_deploy,
)

__all__ = [
    "atomic_replace_item",
    "discover_config_items",
    "deploy_selected_configs",
    "deploy_runtime_conf",
    "render_completion_screen",
    "test_deploy",
    "deploy_assets",
    "assets_present",
    "AssetDeployResult",
    "load_manifest",
    "load_manifest_for",
    "load_optional_apps",
    "discover_manifest_apps",
    "discover_deployable_apps",
    "discover_optional_apps",
    "ModuleManifest",
]
