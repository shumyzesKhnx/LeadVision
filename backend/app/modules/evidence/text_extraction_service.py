"""Saved readable text validation; live HTML extraction follows at the live milestone."""
from app.modules.foundation.errors import AppError

MAX_TEXT_BYTES = 1_000_000
MAX_TEXT_CHARACTERS = 30_000


def validate_saved_text(content: bytes):
    if len(content) > MAX_TEXT_BYTES:
        raise AppError('TEXT_TOO_LARGE', 'Saved text must be at most 1 MB.', 413)
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise AppError('INVALID_TEXT', 'Save the text file as UTF-8.', 422) from None
    if '\x00' in text:
        raise AppError('INVALID_TEXT', 'Choose a readable UTF-8 text file.', 422)
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        raise AppError('EMPTY_TEXT', 'The text file has no readable content.', 422)
    truncated = len(text) > MAX_TEXT_CHARACTERS
    return text[:MAX_TEXT_CHARACTERS], {'characters': min(len(text), MAX_TEXT_CHARACTERS),
                                      'original_characters': len(text), 'truncated': truncated}


def extract_html(content: bytes, url: str, content_type='text/html'):
    from html.parser import HTMLParser
    import re
    from urllib.parse import urljoin, urlsplit
    from app.modules.foundation.urls import normalize_website
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.hidden = []; self.title_depth = 0; self.title = []; self.lines = []; self.links = []
        def handle_starttag(self, tag, attrs):
            if tag in ('script','style','nav','footer','header','noscript','svg','template'): self.hidden.append(tag)
            if tag == 'title': self.title_depth += 1
            if tag in ('p','div','li','h1','h2','h3','br','section'): self.lines.append('\n')
            values = dict(attrs)
            if tag == 'a' and values.get('href'): self.links.append(values['href'])
        def handle_endtag(self, tag):
            if tag in self.hidden:
                index = len(self.hidden) - 1 - self.hidden[::-1].index(tag); del self.hidden[index:]
            if tag == 'title': self.title_depth = max(0, self.title_depth - 1)
            if tag in ('p','div','li','h1','h2','h3','section'): self.lines.append('\n')
        def handle_data(self, data):
            if self.title_depth: self.title.append(data)
            elif not self.hidden: self.lines.append(data + ' ')
    match = re.search(r'charset=["\']?([\w-]+)', content_type, re.I)
    encoding = match[1] if match else 'utf-8'
    try: decoded = content.decode(encoding, errors='replace')
    except LookupError: decoded = content.decode('utf-8', errors='replace')
    reader = Reader(); reader.feed(decoded)
    seen = set(); lines = []
    for line in ''.join(reader.lines).splitlines():
        line = ' '.join(line.split())
        if line and line.casefold() not in seen: seen.add(line.casefold()); lines.append(line)
    text = '\n'.join(lines); links = []
    for link in reader.links:
        try: target = normalize_website(urljoin(url, link)).normalized_url
        except ValueError: continue
        if (urlsplit(target).hostname == urlsplit(url).hostname and target not in links
                and any(word in urlsplit(target).path.casefold() for word in ('about','service'))): links.append(target)
    return {'text': text[:30000], 'title': ' '.join(''.join(reader.title).split())[:500],
        'truncated': len(text) > 30000, 'supporting_urls': links[:2]}
