"""The 'branded' fixture (``tests/site/fixtures/branded``): a Structurizr theme, local overrides, icons and branding."""

from __future__ import annotations

import base64
import struct
import zlib

from buildzr.dsl import (
    Container,
    ContainerView,
    Person,
    SoftwareSystem,
    StyleElements,
    StyleRelationships,
    SystemLandscapeView,
    Workspace,
)
from buildzr.themes import KUBERNETES_V0_3

#: The tag the Kubernetes theme styles with stroke and colour #3d6fdd (and a remote icon, which is not shown).
POD = "Kubernetes - pod"
#: Styled by the theme and by the workspace: the workspace's background and icon win, the theme's stroke stays.
SVC = "Kubernetes - svc"
FONT = "DejaVu Serif, serif"


def png(rgb: tuple[int, int, int], size: int = 16) -> str:
    """A ``size`` x ``size`` PNG of one colour, as a data URI."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


RED, GREEN, BLUE = png((220, 40, 40)), png((40, 160, 60)), png((40, 80, 220))


def branded_workspace() -> Workspace:
    """A shop on Kubernetes: a customer, a shop (API, a pod and a service) and a payment system.

    Styles: the Kubernetes theme (the API and the worker are pods; the theme sets their stroke and text colour and the
    workspace a white background), a local override of the theme's service tag (light green background, green icon),
    a red icon on the customer, a blue icon on the shop (a frame) and a dashed
    relationship style. Branding: a blue logo and the font stack ``DejaVu Serif, serif``.
    """
    with Workspace("Branded Shop", description="Themes, icons and branding.", scope=None) as w:
        customer = Person("Customer", description="Buys things.")
        with SoftwareSystem("Shop", description="Sells things.") as shop:
            api = Container("API", technology="Python", tags={POD})
            worker = Container("Worker", technology="Python", tags={POD})
            svc = Container("Gateway", description="Routes the requests.", technology="Envoy", tags={SVC})
        payments = SoftwareSystem("Payments", description="Takes the money.", tags={"External"})
        customer >> "Uses" >> svc
        svc >> "Forwards to" >> api
        api >> ("Queues jobs for", "AMQP") >> worker
        charges = api >> ("Charges", "HTTPS") >> payments
        w.apply_theme(KUBERNETES_V0_3)
        StyleElements(on=[POD], background="#ffffff")
        StyleElements(on=[SVC], background="#e8f5e9", icon=GREEN)
        StyleElements(on=[customer], icon=RED)
        StyleElements(on=[shop], icon=BLUE)
        StyleElements(on=["External"], background="#6d6d6d")
        StyleRelationships(on=[charges], dashed=True, color="#b23c17")
        w.apply_branding(logo=BLUE, font=FONT)
        SystemLandscapeView(key="landscape", description="Everything.", auto_layout="tb")
        ContainerView(software_system_selector=shop, key="shop", description="The shop.", auto_layout="tb")
    return w
