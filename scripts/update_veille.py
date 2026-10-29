#!/usr/bin/env python3
"""Select one recent RSS article and render it in the portfolio; standard library only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('IT-Connect', 'https://www.it-connect.fr/feed/'),
    ('Numerama', 'https://www.numerama.com/feed/'),
    ('CERT-FR', 'https://cert.cyber.gouv.fr/feed/'),
]
TOPICS = {
    'Réseaux et systèmes': ['reseau', 'reseaux', 'routeur', 'switch', 'wifi', 'wi-fi', 'ethernet', 'dns', 'dhcp', 'serveur', 'linux', 'windows server', 'active directory', 'cloud', 'cisco', 'vpn', 'infrastructure', 'virtualisation'],
    'Cybersécurité': ['cybersecurite', 'cyberattaque', 'vulnerabilite', 'ransomware', 'phishing', 'securite', 'faille', 'correctif', 'pare-feu', 'malware'],
    'Intelligence artificielle': ['intelligence artificielle', 'ia', 'chatgpt', 'openai', 'claude', 'gemini', 'llm', 'machine learning'],
    'Informatique': ['informatique', 'logiciel', 'microsoft', 'ordinateur', 'processeur', 'stockage', 'systeme'],
}
EXPLANATIONS = {
    'Réseaux et systèmes': 'Ce sujet permet de suivre les évolutions des infrastructures et des outils utilisés pour administrer les systèmes et les réseaux.',
    'Cybersécurité': 'Ce sujet permet de suivre les risques de sécurité et les mesures utiles pour protéger les systèmes et les réseaux.',
    'Intelligence artificielle': 'Ce sujet permet de suivre les évolutions de l’IA et de réfléchir à ses usages dans les métiers de l’informatique.',
    'Informatique': 'Ce sujet permet de suivre les évolutions des outils et des technologies du secteur informatique.',
}

def normalise(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')

def classify(title):
    text = normalise(title)
    scores = {topic: sum(bool(re.search(r'\b' + re.escape(term) + r'\b', text)) for term in terms) for topic, terms in TOPICS.items()}
    topic = max(scores, key=scores.get)
    return topic, scores[topic]

def parse_feed(data, source, now):
    root = ET.fromstring(data)
    articles = []
    for item in root.findall('.//item'):
        title = ' '.join((item.findtext('title') or '').split())
        link = (item.findtext('link') or '').strip()
        raw_date = item.findtext('pubDate') or ''
        try:
            published = parsedate_to_datetime(raw_date)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if not title or urllib.parse.urlsplit(link).scheme not in ('http', 'https'):
            continue
        if not now - timedelta(days=7) <= published <= now + timedelta(minutes=5):
            continue
        topic, score = classify(title)
        if score:
            articles.append(dict(title=title[:240], link=link, published=published, source=source, topic=topic, score=score))
    return articles

def fetch(source):
    name, url = source
    request = urllib.request.Request(url, headers={'User-Agent': 'Portfolio-Bechir-RSS/1.0', 'Accept': 'application/rss+xml, application/xml, text/xml'})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = response.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError('Flux trop volumineux')
        return parse_feed(data, name, datetime.now(timezone.utc))
    except Exception as error:
        print(f'::warning::{name} : {type(error).__name__}')
        return []

def choose(articles, now):
    recent = [a for a in articles if a['published'] >= now - timedelta(hours=48)]
    candidates = recent or articles
    if not candidates:
        raise RuntimeError('Aucun article récent pertinent : publication interrompue pour conserver le site existant.')
    # Cap keyword weight so repetition cannot dominate recency; prioritise SISR topics.
    return max(candidates, key=lambda a: (min(a['score'], 3) + (1 if a['topic'] in ('Réseaux et systèmes', 'Cybersécurité') else 0), a['published']))

def render(article, now):
    from zoneinfo import ZoneInfo
    date = article['published'].astimezone(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y')
    checked = now.astimezone(ZoneInfo('Europe/Paris')).strftime('%d/%m/%Y à %H:%M')
    return f'''\n      <div class="projet-badge">{escape(article['topic'])}</div>
      <h4 style="font-size:1.25rem;line-height:1.5;margin-bottom:1rem">{escape(article['title'])}</h4>
      <p>{escape(article['source'])} · Publié le {date}</p>
      <p>{escape(EXPLANATIONS[article['topic']])}</p>
      <a class="projet-link" href="{escape(article['link'], quote=True)}" target="_blank" rel="noopener noreferrer">Lire l’article sur le site source →</a>
      <p style="font-size:0.8rem;margin-top:1rem">Sélection automatique par date et mots-clés · Actualisé le {checked} (heure de Paris). Un même article peut rester affiché si aucune publication plus pertinente n’est trouvée.</p>
      '''

def update_html(html, article, now):
    start, end = '<!-- VEILLE_ARTICLE_START -->', '<!-- VEILLE_ARTICLE_END -->'
    if html.count(start) != 1 or html.count(end) != 1:
        raise ValueError('Repères de veille absents ou ambigus')
    before, remaining = html.split(start)
    _, after = remaining.split(end)
    return before + start + render(article, now) + end + after

def main():
    now = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=3) as pool:
        articles = [a for batch in pool.map(fetch, SOURCES) for a in batch]
    selected = choose(articles, now)
    original = (ROOT / 'index.html').read_text(encoding='utf-8')
    updated = update_html(original, selected, now)
    out = ROOT / '_site'
    out.mkdir(exist_ok=True)
    (out / 'index.html').write_text(updated, encoding='utf-8')
    print(f"Sélection : {selected['source']} — {selected['title']}")

if __name__ == '__main__':
    main()
