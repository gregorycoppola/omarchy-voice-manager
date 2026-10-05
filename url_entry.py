"""Validate a typed web address before passing it to the browser launcher."""
import re
from urllib.parse import urlsplit


def normalize_url(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('Enter a web address, up to 2000 characters.')
    url = text.strip()
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise ValueError('Web addresses cannot contain spaces or control characters.')
    if '://' not in url:
        # A domain with a port is an address; other scheme prefixes are not.
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', url) and not re.match(r'^[^/:]+:\d+(?:/|$)', url):
            raise ValueError('Use an http:// or https:// web address.')
        url = 'https://' + url
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or '\\' in parsed.netloc or parsed.hostname.startswith('-')):
            raise ValueError
    except ValueError:
        raise ValueError('Enter a valid http:// or https:// web address.') from None
    return url
