"""Tests for buildzr theme system."""

import pytest
from unittest.mock import patch, MagicMock
import base64

from buildzr.themes import (
    ThemeElement,
    AWS,
    AZURE,
    GOOGLE_CLOUD,
    KUBERNETES,
    AWS_2023_01_31,
    AWS_2022_04_30,
    AWS_2020_04_30,
)


class TestThemeElement:
    """Tests for ThemeElement dataclass."""

    def test_theme_element_creation(self) -> None:
        """Test creating a ThemeElement."""
        element = ThemeElement(
            tag="Test - Element",
            stroke="#ff0000",
            color="#00ff00",
            icon_url="https://example.com/icon.png",
        )
        assert element.tag == "Test - Element"
        assert element.stroke == "#ff0000"
        assert element.color == "#00ff00"
        assert element.icon_url == "https://example.com/icon.png"

    def test_theme_element_unpacking(self) -> None:
        """Test that ThemeElement can be unpacked with **."""
        element = ThemeElement(
            tag="Test - Element",
            stroke="#ff0000",
            color="#00ff00",
            icon_url="https://example.com/icon.png",
        )
        kwargs = dict(element)
        assert kwargs == {
            'tag': 'Test - Element',
            'stroke': '#ff0000',
            'color': '#00ff00',
            'icon': 'https://example.com/icon.png',
        }

    def test_theme_element_as_inline(self) -> None:
        """Test as_inline() returns base64 icon."""
        element = ThemeElement(
            tag="Test - Element",
            stroke="#ff0000",
            color="#00ff00",
            icon_url="https://example.com/icon.png",
        )

        # Mock the urlopen to avoid network calls
        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_response = MagicMock()
        mock_response.read.return_value = fake_image_data
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('urllib.request.urlopen', return_value=mock_response):
            inline_kwargs = element.as_inline()

        assert inline_kwargs['stroke'] == '#ff0000'
        assert inline_kwargs['color'] == '#00ff00'
        assert inline_kwargs['icon'].startswith('data:image/png;base64,')

        # Verify base64 decodes correctly
        base64_data = inline_kwargs['icon'].split(',')[1]
        decoded = base64.b64decode(base64_data)
        assert decoded == fake_image_data

    def test_theme_element_frozen(self) -> None:
        """Test that ThemeElement is immutable."""
        element = ThemeElement(
            tag="Test",
            stroke="#ff0000",
            color="#00ff00",
            icon_url="https://example.com/icon.png",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            element.tag = "Modified" # type: ignore

class TestGeneratedThemes:
    """Tests for generated theme modules."""

    def test_aws_theme_exists(self) -> None:
        """Test AWS theme is available."""
        assert AWS is not None
        assert AWS.THEME_URL is not None
        assert AWS.THEME_NAME == "Amazon Web Services"

    def test_aws_has_common_services(self) -> None:
        """Test AWS theme has common service icons."""
        # Check some common AWS services exist
        assert hasattr(AWS, 'EC2_INSTANCE')
        assert hasattr(AWS, 'LAMBDA')
        assert hasattr(AWS, 'SIMPLE_STORAGE_SERVICE')  # S3
        assert hasattr(AWS, 'ROUTE_53')

    def test_aws_ec2_instance_structure(self) -> None:
        """Test AWS EC2 instance ThemeElement has correct structure."""
        ec2 = AWS.EC2_INSTANCE
        assert isinstance(ec2, ThemeElement)
        assert ec2.tag == "Amazon Web Services - EC2 Instance"
        assert ec2.stroke.startswith('#')
        assert ec2.color.startswith('#')
        assert ec2.icon_url.startswith('https://')

    def test_azure_theme_exists(self) -> None:
        """Test Azure theme is available."""
        assert AZURE is not None
        assert AZURE.THEME_NAME == "Microsoft Azure"

    def test_google_cloud_theme_exists(self) -> None:
        """Test Google Cloud theme is available."""
        assert GOOGLE_CLOUD is not None
        assert GOOGLE_CLOUD.THEME_NAME == "Google Cloud Platform"

    def test_kubernetes_theme_exists(self) -> None:
        """Test Kubernetes theme is available."""
        assert KUBERNETES is not None
        assert KUBERNETES.THEME_NAME == "Kubernetes"

    def test_aws_version_classes(self) -> None:
        """Test AWS has version-specific classes."""
        assert AWS_2023_01_31 is not None
        assert AWS_2022_04_30 is not None
        assert AWS_2020_04_30 is not None

        # Default should be latest
        assert AWS is AWS_2023_01_31

    def test_all_elements_method(self) -> None:
        """Test all_elements() classmethod returns ThemeElements."""
        elements = AWS.all_elements()
        assert isinstance(elements, list)
        assert len(elements) > 0
        assert all(isinstance(e, ThemeElement) for e in elements)


class TestThemeWithStyleElements:
    """Test integration with StyleElements."""

    def test_unpacking_into_style_elements(self) -> None:
        """Test that theme elements can be unpacked into StyleElements."""
        from buildzr.dsl import Workspace, Container, StyleElements

        with Workspace("Test") as w:
            container = Container("Test Container")

            # This should work without errors
            StyleElements(on=[container], **AWS.EC2_INSTANCE)

        # Verify the style was applied
        styles = w.model.views.configuration.styles.elements
        assert len(styles) > 0

        # Find the style that was applied
        applied_style = None
        for style in styles:
            if style.icon and 'EC2' in style.icon:
                applied_style = style
                break

        assert applied_style is not None
        assert applied_style.stroke == AWS.EC2_INSTANCE.stroke
        assert applied_style.color == AWS.EC2_INSTANCE.color
