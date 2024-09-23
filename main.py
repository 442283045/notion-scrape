import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


def scrape_article(article_url: str) -> Dict[str, str]:
    try:
        response = requests.get(article_url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("h1").text.strip() if soup.find("h1") else ""
        content = soup.find("article")

        if content:
            # Remove unwanted elements
            for element in content(["script", "style", "nav", "footer"]):
                element.decompose()

            # Preserve structure of headers, paragraphs, and lists
            for element in content(["h2", "h3", "h4", "h5", "h6", "p", "ul", "ol"]):
                if element.name.startswith("h"):
                    element.insert_before("\n\n")
                    element.insert_after("\n")
                elif element.name == "p":
                    element.insert_after("\n\n")
                elif element.name in ["ul", "ol"]:
                    element.insert_before("\n")
                    element.insert_after("\n")

            text_content = content.get_text(separator="", strip=True)
            text_content = re.sub(
                r"\n{3,}", "\n\n", text_content
            )  # Remove excess newlines
            return {"title": title, "content": text_content, "url": article_url}
    except Exception as e:
        print(f"Error scraping {article_url}: {str(e)}")
    return None


def scrape_notion_help_center() -> List[Dict[str, str]]:
    base_url = "https://www.notion.so/help"
    response = requests.get(base_url)
    soup = BeautifulSoup(response.text, "html.parser")

    article_links = soup.find_all("a", href=re.compile(r"^/help/"))
    # Filter out Notion Academy links
    article_links = [
        link for link in article_links if "notion.so/help/academy" not in link["href"]
    ]
    print(f"Found {len(article_links)} article links (excluding Notion Academy guides)")

    articles = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {
            executor.submit(
                scrape_article, f"https://www.notion.so{link['href']}"
            ): link
            for link in article_links
        }
        for future in tqdm(
            as_completed(future_to_url),
            total=len(article_links),
            desc="Scraping articles",
        ):
            article = future.result()
            if article:
                articles.append(article)

    return articles


def chunk_content(
    articles: List[Dict[str, str]], max_chunk_size: int = 750
) -> List[str]:
    chunks = []

    for article in articles:
        title = article["title"]
        content = article["content"]

        # Split content into sections based on headers
        sections = re.split(r"(\n\n[A-Z][\w\s]+\n)", content)

        current_chunk = f"{title}\n\n"
        for section in sections:
            if re.match(r"\n\n[A-Z][\w\s]+\n", section):  # This is a header
                if len(current_chunk.strip()) > 0:
                    chunks.append(current_chunk.strip())
                current_chunk = f"{title} - {section.strip()}\n\n"
            else:
                # Further split section into paragraphs and lists
                elements = re.split(r"(\n\n[-*+] .+?(\n|$))", section)
                for element in elements:
                    if not element.strip():
                        continue
                    if re.match(r"\n\n[-*+] .+", element):  # Detected a list
                        list_content = element.strip().replace("\n", " ") + "\n\n"
                        if (
                            len(current_chunk) + len(list_content) > max_chunk_size
                            and len(current_chunk.strip()) > 0
                        ):
                            chunks.append(current_chunk.strip())
                            current_chunk = f"{title} (continued)\n\n"
                        current_chunk += list_content
                    else:  # It's a paragraph
                        paragraph = element.strip() + "\n\n"
                        if (
                            len(current_chunk) + len(paragraph) > max_chunk_size
                            and len(current_chunk.strip()) > 0
                        ):
                            chunks.append(current_chunk.strip())
                            current_chunk = f"{title} (continued)\n\n"
                        current_chunk += paragraph

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

    return chunks


def save_to_json(data: List, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Data saved to {filename}")


def main():
    print("Starting Notion Help Center scraper...")
    start_time = time.time()

    articles = scrape_notion_help_center()
    print(f"Scraped {len(articles)} articles.")

    chunks = chunk_content(articles)
    print(f"Created {len(chunks)} chunks.")

    save_to_json(chunks, "notion_help_chunks.json")
    save_to_json(articles, "notion_help_articles.json")

    end_time = time.time()
    print(f"Scraping completed in {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
