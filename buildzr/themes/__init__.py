"""
buildzr theme system.

Provides IDE-discoverable constants for Structurizr themes
(AWS, Azure, Google Cloud, Kubernetes, Oracle Cloud Infrastructure).

Usage:
    from buildzr.dsl import Workspace, DeploymentNode, StyleElements
    from buildzr.themes import AWS

    with Workspace("AWS App") as w:
        ec2 = DeploymentNode("Amazon EC2")
        StyleElements(on=[ec2], **AWS.EC2_INSTANCE)  # icon=URL

    # For offline/self-contained workspaces, use as_inline():
    StyleElements(on=[ec2], **AWS.EC2_INSTANCE.as_inline())  # icon=base64

    # Use specific theme versions:
    from buildzr.themes import AWS_2022_04_30
    StyleElements(on=[ec2], **AWS_2022_04_30.EC2_INSTANCE)

To regenerate theme modules:
    python -m buildzr.themes.generate --urls-file buildzr/themes/themes.txt
"""

from .base import ThemeElement

# Import generated themes
from .generated import (
    AWS,
    AZURE,
    GOOGLE_CLOUD,
    KUBERNETES,
    ORACLE_CLOUD,
)

# Version-specific imports
from .generated.aws import (
    AWS_2023_01_31,
    AWS_2022_04_30,
    AWS_2020_04_30,
)
from .generated.azure import AZURE_2023_01_24
from .generated.google_cloud import GOOGLE_CLOUD_V1_5
from .generated.kubernetes import KUBERNETES_V0_3
from .generated.oracle_cloud import (
    ORACLE_CLOUD_2023_04_01,
    ORACLE_CLOUD_2021_04_30,
    ORACLE_CLOUD_2020_04_30,
)

__all__ = [
    # Base class
    'ThemeElement',
    # Default aliases (latest versions)
    'AWS',
    'AZURE',
    'GOOGLE_CLOUD',
    'KUBERNETES',
    'ORACLE_CLOUD',
    # Version-specific
    'AWS_2023_01_31',
    'AWS_2022_04_30',
    'AWS_2020_04_30',
    'AZURE_2023_01_24',
    'GOOGLE_CLOUD_V1_5',
    'KUBERNETES_V0_3',
    'ORACLE_CLOUD_2023_04_01',
    'ORACLE_CLOUD_2021_04_30',
    'ORACLE_CLOUD_2020_04_30',
]
