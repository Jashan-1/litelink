import httpx
import pytest

from app.scanner.ssrf import MAX_BYTES, MAX_HOPS, BlockedURL, is_public, safe_fetch

PUBLIC = "93.184.216.34"


def resolver_for(table):
    async def resolver(host, port):
        return table.get(host, [PUBLIC])
    return resolver


def transport(handler):
    return httpx.MockTransport(handler)


def never_called(request):
    raise AssertionError(f"connected to {request.url}")


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "::1", "fe80::1", "fc00::1", "ff02::1",
    "::ffff:127.0.0.1", "::ffff:169.254.169.254", "64:ff9b::7f00:1", "2002:7f00:1::",
])
def test_non_public_addresses_are_rejected(address):
    assert not is_public(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_addresses_pass(address):
    assert is_public(address)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
])
async def test_ip_literals_are_blocked(url):
    async def real_answer(host, port):
        return [host]
    with pytest.raises(BlockedURL):
        await safe_fetch(url, resolver=real_answer, transport=transport(never_called))


async def test_domain_resolving_to_private_ip_is_blocked():
    with pytest.raises(BlockedURL):
        await safe_fetch("https://evil.test/", resolver=resolver_for({"evil.test": ["10.0.0.5"]}), transport=transport(never_called))


async def test_one_private_answer_among_public_ones_is_blocked():
    with pytest.raises(BlockedURL):
        await safe_fetch("https://evil.test/", resolver=resolver_for({"evil.test": [PUBLIC, "127.0.0.1"]}), transport=transport(never_called))


async def test_redirect_to_private_ip_is_blocked():
    def handler(request):
        assert request.headers["host"] == "evil.test"
        return httpx.Response(302, headers={"location": "http://internal.test/admin"})
    with pytest.raises(BlockedURL):
        await safe_fetch("https://evil.test/", resolver=resolver_for({"internal.test": ["192.168.0.2"]}), transport=transport(handler))


async def test_dns_rebinding_cannot_change_the_connected_address():
    answers = iter([[PUBLIC], ["127.0.0.1"]])

    async def rebinding(host, port):
        return next(answers)

    connected = []

    def handler(request):
        connected.append(request.url.host)
        return httpx.Response(200, text="ok")

    result = await safe_fetch("https://rebind.test/", resolver=rebinding, transport=transport(handler))
    assert connected == [PUBLIC]  # the validated address, not the hostname a second lookup would remap
    assert result.status == 200


async def test_host_and_sni_keep_the_real_name_while_connecting_to_the_ip():
    seen = {}

    def handler(request):
        seen.update(host=request.url.host, header=request.headers["host"], sni=request.extensions["sni_hostname"])
        return httpx.Response(200, text="ok")

    await safe_fetch("https://site.test:8443/a?b=1", resolver=resolver_for({}), transport=transport(handler))
    assert seen == {"host": PUBLIC, "header": "site.test:8443", "sni": "site.test"}


async def test_credentials_in_the_url_are_not_sent():
    def handler(request):
        assert "authorization" not in request.headers
        assert b"user" not in request.url.userinfo
        return httpx.Response(200)

    result = await safe_fetch("https://user:pw@site.test/", resolver=resolver_for({}), transport=transport(handler))
    assert "user" not in result.final_url


async def test_relative_redirects_are_followed_and_recorded():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "/end"})
        return httpx.Response(200, text="done")

    result = await safe_fetch("https://site.test/start", resolver=resolver_for({}), transport=transport(handler))
    assert result.chain == ["https://site.test/start", "https://site.test/end"]
    assert result.final_url == "https://site.test/end"
    assert result.body == b"done"


async def test_redirect_loops_stop():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(BlockedURL):
        await safe_fetch("https://site.test/", resolver=resolver_for({}), transport=transport(handler))
    assert len(calls) == MAX_HOPS + 1


async def test_non_http_redirect_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "file:///etc/passwd"})

    with pytest.raises(BlockedURL):
        await safe_fetch("https://site.test/", resolver=resolver_for({}), transport=transport(handler))


async def test_body_is_capped():
    def handler(request):
        return httpx.Response(200, content=b"x" * (MAX_BYTES + 500))

    result = await safe_fetch("https://site.test/", resolver=resolver_for({}), transport=transport(handler))
    assert len(result.body) == MAX_BYTES
    assert result.truncated
