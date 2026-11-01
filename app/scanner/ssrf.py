"""Fetch a URL we don't trust without letting it reach anything internal.

Every hop is resolved once, each resolved address is checked, and the connection
is made to that exact address. Letting httpx resolve the name again would allow
DNS rebinding: public IP at check time, private IP at connect time.
"""
import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field

import httpx

MAX_HOPS = 5
MAX_BYTES = 1_000_000
TIMEOUT_SECONDS = 5
# Global by Python's rules, but they tunnel to an embedded IPv4 address.
TUNNEL_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("64:ff9b::/96", "2002::/16"))


class BlockedURL(Exception):
    pass


@dataclass
class Fetched:
    final_url: str
    status: int
    body: bytes
    truncated: bool
    chain: list[str] = field(default_factory=list)  # every URL visited, in order


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])  # drop any IPv6 zone id
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast and not any(ip in net for net in TUNNEL_NETWORKS)


async def resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def _public_ip(url: httpx.URL, resolver) -> str:
    if url.scheme not in ("http", "https") or not url.host:
        raise BlockedURL(f"unsupported URL: {url}")
    addresses = await resolver(url.host, url.port or (443 if url.scheme == "https" else 80))
    # One private answer rejects the name: a client may try the addresses in any order.
    if not addresses or not all(is_public(a) for a in addresses):
        raise BlockedURL(f"{url.host} resolves to a non-public address")
    return addresses[0]


async def safe_fetch(url: str, *, resolver=resolve, transport: httpx.AsyncBaseTransport | None = None) -> Fetched:
    """GET url, following redirects itself. Raises BlockedURL, TimeoutError or httpx/socket errors."""
    chain: list[str] = []
    async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False) as client:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            for _ in range(MAX_HOPS + 1):
                current = httpx.URL(url).copy_with(username=None, password=None)
                chain.append(str(current))
                pinned = current.copy_with(host=await _public_ip(current, resolver))
                headers = {
                    "Host": current.netloc.decode(),
                    "User-Agent": "LiteLink-Scanner/0.1",
                    "Accept-Encoding": "identity",  # no compressed bombs past the size cap
                }
                # sni_hostname keeps TLS and certificate checks on the real name, not the IP.
                async with client.stream(
                    "GET", pinned, headers=headers, extensions={"sni_hostname": current.host}
                ) as response:
                    if response.has_redirect_location:
                        url = str(current.join(response.headers["location"]))
                        continue
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return Fetched(
                        str(current), response.status_code, bytes(body[:MAX_BYTES]), len(body) > MAX_BYTES, chain
                    )
    raise BlockedURL(f"more than {MAX_HOPS} redirects")
