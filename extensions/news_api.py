

import datetime
import requests

from library_data.blacklist import blacklist
from utils.config import config
from utils.utils import Utils


class NewsResponse:
    def __init__(self, resp_json, country="us"):
        self.country = country.upper()
        self.datetime = datetime.datetime.now().strftime("%A %B %d at %H:%M")
        self.status = resp_json["status"]
        self.totalResults = resp_json["totalResults"]
        self.articles = resp_json["articles"]

    def get_source_trustworthiness(self, source_name):
        if source_name in config.news_api_source_trustworthiness:
            return config.news_api_source_trustworthiness[source_name]
        Utils.log(f"No trustworthiness score found for News API propaganda source {source_name}")
        return 0.25

    def get_trustworthy_and_nonblacklisted_stories(self):
        headlines = []
        for article in self.articles:
            source_name = article["source"]["name"]
            trustworthiness = self.get_source_trustworthiness(source_name)
            if trustworthiness > 0.2:
                blacklist_items = blacklist.test_all(article['title'])
                if len(blacklist_items) > 0:
                    title = article['title']
                    Utils.log(f"Article blacklisted: {title} ({blacklist_items})")
                else:
                    headlines.append(article)
        return headlines

    def __str__(self):
        out = f"Latest Propaganda for {self.country} on {self.datetime}"
        for article in self.get_trustworthy_and_nonblacklisted_stories():
            title = article['title']
            source_name = article['source']['name']
            trustworthiness = self.get_source_trustworthiness(source_name)
            out += f"\n{title} - Propaganda Source {source_name} (Trustworthiness score: {trustworthiness})"
        return out

class NewsAPI:
    ENDPOINT = "https://newsapi.org/v2/top-headlines"
    KEY = config.news_api_key

    def __init__(self) -> None:
        pass

    def get_news(self, country="us", topic=None) -> NewsResponse:
        url = f"{self.ENDPOINT}?country={country}&apiKey={NewsAPI.KEY}"
        if topic is not None:
            url += "&q={}".format(topic)
        news = NewsResponse(requests.get(url).json(), country)
        return news


if __name__ == "__main__":
    news = NewsAPI()
    Utils.log(news.get_news())

