"""Tests for buildzr theme system."""

import json
import pytest
from pathlib import Path
import re
from typing import Any, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import base64

from buildzr.themes import (
    ThemeElement,
    AWS,
    AZURE,
    GOOGLE_CLOUD,
    KUBERNETES,
    ORACLE_CLOUD,
    AWS_2023_01_31,
    AWS_2022_04_30,
    AWS_2020_04_30,
)
from buildzr.themes import KUBERNETES_V0_3, assets
from buildzr.themes.generate import read_urls_file

ROOT = Path(__file__).parent.parent
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


class FakeResponse:
    def __init__(self, url: str, data: bytes, final: Optional[str] = None) -> None:
        self.url, self.data, self.final = url, data, final or url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def geturl(self) -> str:
        return self.final

    def read(self, n: int = -1) -> bytes:
        return self.data if n < 0 else self.data[:n]


class FakeHost:
    """Stands in for ``urllib.request.urlopen``: ``files`` maps a URL to its bytes, or to an exception to raise."""

    def __init__(self, files: dict[str, Any], redirect: Optional[str] = None) -> None:
        self.files, self.redirect = files, redirect
        self.calls: list[tuple[str, Any]] = []

    def __call__(self, req: Request, timeout: Any = None) -> FakeResponse:
        url = req.full_url
        self.calls.append((url, timeout))
        got = self.files.get(url)
        if isinstance(got, BaseException):
            raise got
        if got is None:
            raise HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        return FakeResponse(url, got, self.redirect)


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

    def test_theme_element_as_inline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test as_inline() returns base64 icon."""
        element = ThemeElement(
            tag="Test - Element",
            stroke="#ff0000",
            color="#00ff00",
            icon_url="https://example.com/icon.png",
        )

        # Fake the host to avoid network calls
        fake_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        monkeypatch.delenv(assets.OFFLINE_ENV)
        monkeypatch.setattr(assets, "_urlopen", FakeHost({element.icon_url: fake_image_data}))
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

    def test_oracle_cloud_theme_exists(self) -> None:
        """Test Oracle Cloud theme is available."""
        assert ORACLE_CLOUD is not None
        assert ORACLE_CLOUD.THEME_NAME == "Oracle Cloud Infrastructure"
        # Check some common OCI services exist
        assert hasattr(ORACLE_CLOUD, 'AUTONOMOUS_DATABASE')
        assert hasattr(ORACLE_CLOUD, 'FUNCTIONS')

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


class TestThemeURLsValidity:
    """Tests to verify all theme URLs in themes.txt are valid and fetchable."""

    @pytest.fixture
    def theme_urls(self) -> list[str]:
        """Read all theme URLs from themes.txt."""
        themes_file = Path(__file__).parent.parent / "buildzr" / "themes" / "themes.txt"
        return read_urls_file(themes_file)

    @pytest.mark.network
    def test_all_theme_urls_are_fetchable(self, theme_urls: list[str]) -> None:
        """Test that all theme URLs in themes.txt can be fetched."""
        for url in theme_urls:
            try:
                with urlopen(url, timeout=30) as response:
                    assert response.status == 200, f"Failed to fetch {url}: status {response.status}"
            except URLError as e:
                pytest.fail(f"Failed to fetch {url}: {e}")

    @pytest.mark.network
    def test_all_theme_jsons_have_valid_structure(self, theme_urls: list[str]) -> None:
        """Test that all theme JSONs have the expected Structurizr theme structure."""
        for url in theme_urls:
            with urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            # Required top-level fields
            assert "name" in data, f"Theme {url} missing 'name' field"
            assert isinstance(data["name"], str), f"Theme {url} 'name' should be string"
            assert len(data["name"]) > 0, f"Theme {url} 'name' should not be empty"

            assert "elements" in data, f"Theme {url} missing 'elements' field"
            assert isinstance(data["elements"], list), f"Theme {url} 'elements' should be list"
            assert len(data["elements"]) > 0, f"Theme {url} should have at least one element"

    @pytest.mark.network
    def test_all_theme_elements_have_required_fields(self, theme_urls: list[str]) -> None:
        """Test that all theme elements have required fields."""
        for url in theme_urls:
            with urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

            for i, element in enumerate(data["elements"]):
                # Each element must have a tag
                assert "tag" in element, f"Theme {url} element[{i}] missing 'tag'"
                assert isinstance(element["tag"], str), f"Theme {url} element[{i}] 'tag' should be string"
                assert len(element["tag"]) > 0, f"Theme {url} element[{i}] 'tag' should not be empty"

                # Elements typically have icon, stroke, color (but may be optional in some themes)
                # At minimum, an icon should be present for useful theming
                if "icon" in element:
                    assert isinstance(element["icon"], str), f"Theme {url} element[{i}] 'icon' should be string"

                if "stroke" in element:
                    assert isinstance(element["stroke"], str), f"Theme {url} element[{i}] 'stroke' should be string"

                if "color" in element:
                    assert isinstance(element["color"], str), f"Theme {url} element[{i}] 'color' should be string"

    @pytest.mark.network
    def test_theme_names_match_expected_providers(self, theme_urls: list[str]) -> None:
        """Test that themes are from expected cloud providers."""
        expected_providers = {
            "Amazon Web Services",
            "Microsoft Azure",
            "Google Cloud Platform",
            "Kubernetes",
            "Oracle Cloud Infrastructure",
        }

        found_providers: set[str] = set()
        for url in theme_urls:
            with urlopen(url, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            found_providers.add(data["name"])

        # All found providers should be in expected set
        for provider in found_providers:
            assert provider in expected_providers, f"Unexpected theme provider: {provider}"

        # All expected providers should be found
        for provider in expected_providers:
            assert provider in found_providers, f"Missing theme provider: {provider}"


POD = KUBERNETES_V0_3.POD.icon_url


class TestPin:
    """Every theme and icon URL names one full structurizr/themes commit (#152, #153)."""

    def test_the_pin_is_a_full_commit_sha_and_the_urls_file_uses_it(self) -> None:
        assert assets.is_full_sha(assets.THEMES_COMMIT)
        text = (ROOT / "buildzr" / "themes" / "themes.txt").read_text()
        assert re.findall(r"^@ref (\S+)$", text, re.M) == [assets.THEMES_COMMIT]

    def test_every_generated_theme_and_icon_url_is_pinned(self) -> None:
        for path in (ROOT / "buildzr" / "themes" / "generated").glob("*.py"):
            for url in re.findall(r'"(https?://[^"]+)"', path.read_text()):
                assert url.startswith(assets.PINNED_BASE), f"{path.name}: {url}"
        assert len(assets.known_icons()) > 1000

    def test_no_source_or_packaged_file_names_another_ref_of_the_themes_repository(self) -> None:
        refs = re.compile(r"(?:raw\.githubusercontent\.com|github\.com)/structurizr/themes/(?:(?:raw|blob|tree)/)?"
                          r"([^/\s\"'{]+)/")
        found = []
        for path in sorted((ROOT / "buildzr").rglob("*")):
            if path.is_file() and path.suffix in (".py", ".txt", ".json", ".md", ".js", ".html") \
                    and "__pycache__" not in path.parts:
                found += [(path.name, r) for r in refs.findall(path.read_text(errors="replace"))
                          if r != assets.THEMES_COMMIT]
        assert found == []

    @pytest.mark.parametrize("ref", ["master", "main", "latest", "v1.0", "67da2b5", assets.THEMES_COMMIT.upper()])
    def test_the_urls_file_refuses_a_ref_that_is_not_a_full_commit_sha(self, tmp_path: Path, ref: str) -> None:
        f = tmp_path / "themes.txt"
        f.write_text(f"@ref {ref}\nhttps://raw.githubusercontent.com/structurizr/themes/{{ref}}/x/theme.json\n")
        with pytest.raises(ValueError, match="full 40 digit commit SHA"):
            read_urls_file(f)

    @pytest.mark.parametrize("url", [
        POD,
        POD.replace(assets.THEMES_COMMIT, "master"),
        POD.replace(assets.THEMES_COMMIT, "main"),
        "https://static.structurizr.com/themes/kubernetes-v0.3/pod-256.png",
    ])
    def test_an_icon_of_a_shipped_theme_maps_to_its_pinned_url(self, url: str) -> None:
        assert assets.pinned_url(url) == POD

    @pytest.mark.parametrize("url", [
        "http://raw.githubusercontent.com/structurizr/themes/master/kubernetes-v0.3/pod-256.png",
        "https://static.structurizr.com/themes/kubernetes-v0.3/not-an-icon.png",
        "https://static.structurizr.com/themes/kubernetes-v0.3/pod-256.png?x=1",
        "https://raw.githubusercontent.com/someone/themes/master/kubernetes-v0.3/pod-256.png",
        "https://raw.githubusercontent.com/structurizr/themes/master/kubernetes-v0.3/../kubernetes-v0.3/pod-256.png",
        "https://example.com/kubernetes-v0.3/pod-256.png",
    ])
    def test_any_other_url_has_no_pinned_url(self, url: str) -> None:
        assert assets.pinned_url(url) is None


class TestFetchIcon:
    """A theme icon is fetched from the pinned commit once, checked and cached; the cache needs no network."""

    @pytest.fixture
    def online(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        monkeypatch.delenv(assets.OFFLINE_ENV)
        monkeypatch.setenv(assets.CACHE_ENV, str(tmp_path))
        return tmp_path

    def test_an_icon_is_fetched_once_with_a_timeout_and_then_read_from_the_cache(
            self, online: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        host = FakeHost({POD: PNG})
        monkeypatch.setattr(assets, "_urlopen", host)
        uri = assets.fetch_icon(POD.replace(assets.THEMES_COMMIT, "master"))
        assert uri == "data:image/png;base64," + base64.b64encode(PNG).decode()
        assert host.calls == [(POD, assets.TIMEOUT)]
        cached = online / f"themes-{assets.THEMES_COMMIT}" / "kubernetes-v0.3" / "pod-256.png"
        assert cached.read_bytes() == PNG
        monkeypatch.setenv(assets.OFFLINE_ENV, "1")
        assert assets.fetch_icon(POD) == uri and len(host.calls) == 1

    def test_offline_an_icon_not_in_the_cache_is_an_error_that_names_the_cache(
            self, online: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        host = FakeHost({POD: PNG})
        monkeypatch.setattr(assets, "_urlopen", host)
        monkeypatch.setenv(assets.OFFLINE_ENV, "1")
        with pytest.raises(assets.IconFetchError, match="not in the cache .*BUILDZR_OFFLINE is set") as e:
            assets.fetch_icon(POD)
        assert e.value.network and host.calls == []
        monkeypatch.delenv(assets.OFFLINE_ENV)
        with pytest.raises(assets.IconFetchError, match="the network is not used"):
            assets.fetch_icon(POD, network=False)

    @pytest.mark.parametrize("answer, says, network", [
        (HTTPError(POD, 404, "Not Found", {}, None), "HTTP 404 Not Found", False),  # type: ignore[arg-type]
        (URLError("Name or service not known"), "could not reach the host", True),
        (TimeoutError("timed out"), "could not reach the host", True),
        (b"<html>rate limited</html>", "not a PNG, JPEG, GIF, WebP or SVG image", False),
        (b"", "is 0 bytes", False),
        (PNG + b"\x00" * assets.MAX_ICON_BYTES, f"is {assets.MAX_ICON_BYTES + 1} bytes", False),
    ])
    def test_a_failed_or_unusable_download_is_an_error_and_is_not_cached(
            self, online: Path, monkeypatch: pytest.MonkeyPatch, answer: Any, says: str, network: bool) -> None:
        monkeypatch.setattr(assets, "_urlopen", FakeHost({POD: answer}))
        with pytest.raises(assets.IconFetchError, match=re.escape(says)) as e:
            assets.fetch_icon(POD)
        assert e.value.network == network
        assert not list(online.rglob("*.png"))

    def test_the_real_opener_follows_no_redirect(self) -> None:
        handler = assets._NoRedirect()
        req = Request(POD)
        with pytest.raises(HTTPError, match="a redirect to https://example.com/x.png .not followed."):
            handler.redirect_request(req, None, 302, "Found", {}, "https://example.com/x.png")

    def test_the_real_opener_stops_at_a_redirect_of_a_real_server(self) -> None:
        import http.server
        import threading

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/moved":
                    self.send_response(302)
                    self.send_header("Location", "/elsewhere")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(PNG)
                    served.append(self.path)

            def log_message(self, *args: Any) -> None:
                return None

        served: list[str] = []
        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with pytest.raises(assets.IconFetchError, match="HTTP 302 .*/elsewhere .not followed.") as e:
                assets._download(base + "/moved")
            assert not e.value.network and served == []
            assert assets._download(base + "/icon.png") == PNG
        finally:
            server.shutdown()
            server.server_close()

    def test_a_redirect_is_refused(self, online: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(assets, "_urlopen", FakeHost({POD: PNG}, redirect="https://example.com/pod.png"))
        with pytest.raises(assets.IconFetchError, match="redirected to https://example.com/pod.png"):
            assets.fetch_icon(POD)

    def test_a_damaged_cache_file_is_fetched_again(self, online: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cached = online / f"themes-{assets.THEMES_COMMIT}" / "kubernetes-v0.3" / "pod-256.png"
        cached.parent.mkdir(parents=True)
        cached.write_bytes(b"<html>half a file")
        monkeypatch.setattr(assets, "_urlopen", FakeHost({POD: PNG}))
        assert assets.fetch_icon(POD).endswith(base64.b64encode(PNG).decode())
        assert cached.read_bytes() == PNG

    def test_as_inline_of_a_theme_element_uses_the_pinned_cache(
            self, online: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        host = FakeHost({POD: PNG})
        monkeypatch.setattr(assets, "_urlopen", host)
        el = ThemeElement(tag="t", stroke="#000000", color="#000000", icon_url=POD)
        assert el.as_inline()["icon"] == "data:image/png;base64," + base64.b64encode(PNG).decode()
        assert (online / f"themes-{assets.THEMES_COMMIT}" / "kubernetes-v0.3" / "pod-256.png").is_file()

    @pytest.mark.parametrize("data, mime", [
        (PNG, "image/png"), (b"\xff\xd8\xff\xe0rest", "image/jpeg"), (b"GIF89a....", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"), (b'\xef\xbb\xbf<?xml version="1.0"?><svg/>', "image/svg+xml"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"), (b"<html><svg/></html>", None),
    ])
    def test_the_image_type_comes_from_the_bytes(self, data: bytes, mime: Optional[str]) -> None:
        assert assets.image_type(data) == mime

    @pytest.mark.network
    def test_a_real_pinned_icon_downloads(self, online: Path) -> None:
        assert assets.fetch_icon(POD).startswith("data:image/png;base64,iVBORw0KGgo")
