# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/02_feeds.ipynb.

# %% auto 0
__all__ = ['Feed', 'Article', 'connect_feeds_db', 'create_feeds_db', 'create_articles_db', 'get_small_web_feeds',
           'get_feed_id_from_url', 'gen_ids_index', 'process_removed_feed_from_index', 'download_feed', 'sync_feeds',
           'detect_language', 'parse_feed', 'sync_feeds_db_from_cache', 'get_articles_lang_per_feeds',
           'update_feeds_with_languages', 'get_non_english_feeds', 'get_cleaned_small_web_index', 'diff_index_file',
           'is_feed_english', 'validate_new_index_file']

# %% ../nbs/02_feeds.ipynb 3
import concurrent.futures
import datetime
import feedparser
import os
import re 
import requests
import sqlite3
from collections import namedtuple
from langdetect import detect
from rich import print
from rich.progress import Progress

# %% ../nbs/02_feeds.ipynb 6
def connect_feeds_db() -> sqlite3.Connection:
    """Connect to the feeds database"""
    db_folder = os.environ.get('DB_PATH').rstrip('/')

    # create the db folder if not already existing
    if not os.path.exists(db_folder):
        os.makedirs(db_folder)

    conn = sqlite3.connect(f"{db_folder}/feeds.db")
    return conn

# %% ../nbs/02_feeds.ipynb 8
def create_feeds_db(conn: sqlite3.Connection):
    """Create the feeds database"""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS feeds
                 (id str PRIMARY KEY, 
                  url text,                    
                  title text, 
                  description text, 
                  lang str,
                  feed_type str,
                  license str)''')
    c.close()
    conn.commit()

def create_articles_db(conn: sqlite3.Connection):
    """Create the articles database"""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS articles
                 (id str PRIMARY KEY, 
                  feed_id str, 
                  title text, 
                  content text, 
                  creation_date datetime,
                  lang str,
                  license str, 
                  FOREIGN KEY (feed_id) REFERENCES feeds(feed_id))''')
    c.close()
    conn.commit()

# %% ../nbs/02_feeds.ipynb 11
def get_small_web_feeds() -> list:
    """Get smallweb feeds from KagiSearch's github repository"""
    response = requests.get('https://raw.githubusercontent.com/kagisearch/smallweb/main/smallweb.txt')

    # Check if the request was successful
    if response.status_code == 200:
        # split the response into a list of lines
        return response.text.splitlines()
    else:
        return []

# %% ../nbs/02_feeds.ipynb 15
def get_feed_id_from_url(url: str) -> str:
    """Get the feed id from a feed url"""
    # Make feed folder name from URL by keeping alphanumeric characters only, and replacing everything else with a dash
    return ''.join(ch if ch.isalnum() else '-' for ch in url)

# %% ../nbs/02_feeds.ipynb 19
def gen_ids_index(index: list) -> list:
    """Return a list of IDs of the feeds in the index"""
    return [get_feed_id_from_url(url) for url in index]

# %% ../nbs/02_feeds.ipynb 22
def process_removed_feed_from_index(index: list):
    """Process all the feeds that got removed from the SmallWeb index"""

    conn = connect_feeds_db()
    c = conn.cursor()
    ids_index = gen_ids_index(index)

    # get all the current feeds from FEEDS_PATH
    for folder in os.listdir(os.environ.get('FEEDS_PATH')):
        if folder not in ids_index:
            # remove the feed folder
            os.system(f'rm -rf {folder}')

            # remove from the database            
            
            c.execute(f"DELETE FROM articles WHERE feed_id = '{folder}'")
            c.execute(f"DELETE FROM feeds WHERE id = '{folder}'")
            conn.commit()

    c.close()
    conn.close()            

# %% ../nbs/02_feeds.ipynb 24
def download_feed(url: str):
    """Download a feed from a given url"""

    # create a folder for the feed if not already existing
    folder_path = f"{os.environ.get('FEEDS_PATH').rstrip('/')}/{get_feed_id_from_url(url)}"
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        
    # Create the DDMMYYYY folder if it is not already existing
    date_folder_path = f"{folder_path}/{datetime.datetime.now().strftime('%d%m%Y')}"
    if not os.path.exists(date_folder_path):
        os.makedirs(date_folder_path)

    # only download if feed.xml is not existing
    if not os.path.exists(f"{date_folder_path}/feed.xml"):
        # Download the feed
        response = requests.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Save the feed to the DDMMYYYY folder
            with open(f"{date_folder_path}/feed.xml", 'w') as f:
                f.write(response.text)
            #print(f"Downloaded feed from {url} to {date_folder_path}")
        else:
            print(f"Failed to download feed from {url}")

# %% ../nbs/02_feeds.ipynb 26
def sync_feeds():
    """Sync all feeds from smallweb"""

    feeds = get_small_web_feeds()

    print("[cyan] Clean removed feed from the Small Web index...")
    process_removed_feed_from_index(feeds)

    with Progress() as progress:
        task = progress.add_task("[cyan]Downloading feeds locally...", total=len(feeds))

        def progress_indicator(future):
            "Local progress indicator callback for the concurrent.futures module."
            if not progress.finished:
                progress.update(task, advance=1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for url in feeds:

                futures = [executor.submit(download_feed, url)]

                # register the progress indicator callback for each of the future
                for future in futures:
                    future.add_done_callback(progress_indicator)

# %% ../nbs/02_feeds.ipynb 28
def detect_language(text: str):
    """Detect the language of a given text"""

    # remove all HTML tags from text
    text = re.sub('<[^<]+?>', '', text)

    # remove all HTML entities from text
    text = re.sub('&[^;]+;', '', text)

    # remove all extra spaces
    text = ' '.join(text.split())

    # return if the text is too short
    if len(text) < 64:
        return ''

    # limit the text to 4096 characters to speed up the 
    # language detection processing
    text = text[:4096]

    try:
        lang = detect(text)
    except:
        # if langdetect returns an errors because it can't read the charset, 
        # simply return an empty string to indicate that we can't detect
        # the language
        return ''

    return lang

# %% ../nbs/02_feeds.ipynb 32
Feed = namedtuple('Feed', ['id', 'url', 'title', 'description', 'lang', 'feed_type', 'license'])
Article = namedtuple('Article', ['url', 'feed', 'title', 'content', 'creation_date', 'lang', 'license'])

def parse_feed(url: str, feed_path: str = None):
    """Parse a feed from a given path and url"""

    feed_id = get_feed_id_from_url(url)

    parsed = None
    if feed_path is None:
        parsed = feedparser.parse(url)
    else:
        parsed = feedparser.parse(feed_path)

    feed_title = parsed.feed.get('title', '')
    feed_description = parsed.feed.get('description', '')

    feed = Feed(feed_id,
                url,
                feed_title, 
                feed_description,
                detect_language(feed_title + feed_description),
                parsed.get('version', ''),
                parsed.get('license', ''))

    articles = []
    for entry in parsed.entries:
        article_title = entry.get('title', '')
        article_content = entry.description if 'description' in entry else entry.content if 'content' in entry else ''
        articles.append(Article(entry.get('link', ''),
                                feed_id,
                                article_title,
                                article_content,
                                entry.published if 'published_parsed' in entry else datetime.datetime.now(),
                                detect_language(article_title + article_content),
                                entry.get('license', '')))
    return feed, articles

# %% ../nbs/02_feeds.ipynb 34
def sync_feeds():
    """Sync all feeds from smallweb"""

    feeds = get_small_web_feeds()

    print("[cyan] Clean removed feed from the Small Web index...")
    process_removed_feed_from_index(feeds)

    with Progress() as progress:
        task = progress.add_task("[cyan]Downloading feeds locally...", total=len(feeds))

        def progress_indicator(future):
            "Local progress indicator callback for the concurrent.futures module."
            if not progress.finished:
                progress.update(task, advance=1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for url in feeds:

                futures = [executor.submit(download_feed, url)]

                # register the progress indicator callback for each of the future
                for future in futures:
                    future.add_done_callback(progress_indicator)

def sync_feeds_db_from_cache(ddmmyyyy: str = datetime.datetime.now().strftime('%d%m%Y')):
    """Sync the feeds database from the cache. The cache by default to use is the one from today.
    It is possible to use a different cache by passing a different date in the format DDMMYYYY"""
    conn = connect_feeds_db()

    c = conn.cursor()

    urls = get_small_web_feeds()

    with Progress() as progress:

        task = progress.add_task("[cyan]Synching feeds DB from local cache...", total=len(urls))

        for url in urls:
            feed_id = get_feed_id_from_url(url)
            feed_folder = f"{os.environ.get('FEEDS_PATH').rstrip('/')}/{feed_id}"

            # it is possible the feed was not reachable last time it got scraped
            if not os.path.exists(feed_folder):
                progress.update(task, advance=1)
                continue

            # get the feed.xml path
            feed_path = f"{feed_folder}/{ddmmyyyy}/feed.xml"

            # if file does not exist, skip
            if not os.path.exists(feed_path):
                progress.update(task, advance=1)
                continue

            # parse the feed
            feed, articles = parse_feed(url, feed_path)

            # insert the feed into the database
            c.execute("INSERT OR IGNORE INTO feeds VALUES (?, ?, ?, ?, ?, ?, ?)", feed)

            # insert the articles into the database
            c.executemany("INSERT OR IGNORE INTO articles VALUES (?, ?, ?, ?, ?, ?, ?)", articles),

            conn.commit() 

            progress.update(task, advance=1)
    c.close()
    conn.close()

# %% ../nbs/02_feeds.ipynb 36
def get_articles_lang_per_feeds():
    """Get the count of articles per language per feed"""
    conn = connect_feeds_db()
    c = conn.cursor()
    c.execute('''SELECT
                    fa.language,
                    fa.id
                 FROM (
                    SELECT
                        feeds.id,
                        feeds.url,
                        articles.lang AS language,
                        COUNT(*) AS lang_count
                    FROM feeds
                    LEFT JOIN articles ON articles.feed_id = feeds.id
                    GROUP BY feeds.id, feeds.url, articles.lang
                    ORDER BY feeds.id, lang_count DESC
                 ) AS fa
                            
                 GROUP BY fa.id''')
    rows = c.fetchall()
    conn.close()

    return rows

# %% ../nbs/02_feeds.ipynb 38
def update_feeds_with_languages(rows):
    """Update the feeds database with the language of the feed"""
    conn = connect_feeds_db()
    c = conn.cursor()
    c.executemany("UPDATE feeds SET lang = ? WHERE id = ?", rows)
    conn.commit()
    conn.close()

# %% ../nbs/02_feeds.ipynb 40
def get_non_english_feeds():
    """Return the list of non-english feeds URL"""
    conn = connect_feeds_db()
    c = conn.cursor()
    c.execute('''SELECT url 
                 FROM feeds 
                 WHERE lang <> 'en' and lang <> '' 
                 ORDER BY lang DESC''')
    rows = c.fetchall()
    conn.close()

    return rows

# %% ../nbs/02_feeds.ipynb 42
def get_cleaned_small_web_index():
    """Return the cleaned small web index"""

    index = get_small_web_feeds()
    non_english_feeds = get_non_english_feeds()

    # remove non-english feeds from the index
    for feed in non_english_feeds:
        index.remove(feed[0])

    # order the index by feed id
    index.sort()

    # write the index in a new text file
    with open('smallweb.txt', 'w') as f:
        for url in index:
            f.write(f"{url}\n")

    return index

# %% ../nbs/02_feeds.ipynb 44
def diff_index_file(new_index_file: str):
    """Diff an input index file with the one currently on the `main` 
    branch of the SmallWeb repository"""

    index = get_small_web_feeds()

    # read the new index file
    new_index = ''
    with open(new_index_file, 'r') as f:
        new_index = f.read()

    # get the diff between the two files
    diff_new = list(set(new_index.splitlines()) - set(index))
    diff_removed = list(set(index) - set(new_index.splitlines()))


    return diff_new, diff_removed


# %% ../nbs/02_feeds.ipynb 46
def is_feed_english(url: str):
    """Validate a feed from a given url is an English feed"""

    feed_id = get_feed_id_from_url(url)
    feed_folder = f"{os.environ.get('FEEDS_PATH').rstrip('/')}/{feed_id}"

    # parse the feed
    feed, articles = parse_feed(url)

    # determine if the feed is in English according to the language of each of its articles.
    # We create a statistic of the language used within the feed, if the majority of the articles
    # are in English, we consider the feed to be in English
    lang_count = {}
    for article in articles:
        if article.lang not in lang_count:
            lang_count[article.lang] = 1
        else:
            lang_count[article.lang] += 1

    # determine that the feed is in English if the majority of the articles are in English
    feed_lang = ''
    if len(lang_count) > 0:
        feed_lang = max(lang_count, key=lang_count.get)

    if(feed_lang == 'en'):
        return True
    else:
        return False

# %% ../nbs/02_feeds.ipynb 48
def validate_new_index_file(new_index_file: str):
    """Validate a new index file by checking that all the feeds are in English.
    Returns an empty list if the new feeds are all valid. Returns a list of
    URLs with each of the feed that are not valid."""

    new, _ = diff_index_file(new_index_file)

    # validate that all the new feeds are in English
    invalid_feeds = []
    for url in new:
        if not is_feed_english(url):
            invalid_feeds.append(url)
    
    return invalid_feeds
