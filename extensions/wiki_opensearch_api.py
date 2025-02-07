
import requests

from extensions.soup_utils import SoupUtils
from utils.utils import Utils


class WikiOpenSearchResponse:
    def __init__(self, json: dict) -> None:
        self._json = json
        self.query = json[0]
        self.articles = []
        if len(self._json[1])!= len(self._json[3]):
            raise ValueError('Invalid JSON format, different number of titles and URLs found')
        for i in range(len(self._json[1])):
            self.articles.append((self._json[1][i], self._json[3][i]))

class RandomWikiResponse:
    def __init__(self, json: dict) -> None:
        self._json = json
        pages_content = json["query"]["pages"]
        page_content_key = list(pages_content.keys())[0]
        page_content = pages_content[page_content_key]
        self.title = page_content['title']
        self.data = SoupUtils.remove_tags(page_content['extract'].replace('\n', ''))

    def is_valid(self) -> bool:
        return self.title is not None and self.title != "" and self.data is not None and self.data != ""

    def __str__(self) -> str:
        return self.title + '\n\n' + self.data

class WikiOpenSearchAPI:
    BASE_URL = 'https://en.wikipedia.org/w/api.php'

    def __init__(self) -> None:
        pass

    def __build_url(self, query: str, limit):
        url = f'{self.BASE_URL}?action=opensearch&search={query}&format=json'
        if limit > 0:
            url += f'&limit={limit}'
        return url

    def search(self, query: str, limit=-1):
        try:
            req = requests.get(self.__build_url(query, limit))
            return WikiOpenSearchResponse(req.json())
        except Exception as e:
            Utils.log_red(f"Failed to connect to Wiki OpenSearch API: {e}")
            return None

    def random_wiki(self):
        try:
            req = requests.get(f'{self.BASE_URL}?action=query&generator=random&grnnamespace=0&grnlimit=1&prop=extracts&format=json')
            return RandomWikiResponse(req.json())
        except Exception as e:
            Utils.log_red(f"Failed to connect to Wiki OpenSearch API: {e}")

