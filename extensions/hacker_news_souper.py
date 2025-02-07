import datetime

from extensions.soup_utils import SoupUtils
from library_data.blacklist import blacklist
from utils.utils import Utils


class HackerNewsItem:
    def __init__(self, id, titleline_el):
        titleline_links = SoupUtils.get_elements(class_path=[["tag", "a"]], parent=titleline_el)
        if len(titleline_links) > 2:
            Utils.log_yellow("Unexpected number of title line links found: " + str(len(titleline_links)))
        elif len(titleline_links) == 1:
            return # No source == no item
        elif len(titleline_links) == 0:
            Utils.log_yellow(titleline_el)
            raise Exception("No title line links found: " + str(len(titleline_links)))
        self.id = id
        self.title = titleline_links[0].text
        self.url = titleline_links[0].attrs["href"]
        self.source = titleline_links[1].text if len(titleline_links) > 1 else ""
        self.points = -1
        self.user = None
        self.age = datetime.datetime.strptime("1/1/1970", "%d/%m/%Y")
        self.comments = -1

    def update_for_subline(self, subline_el):
        score_el = subline_el.find(class_="score")
        age_str = subline_el.find(class_="age").attrs["title"]
        date = datetime.datetime.fromtimestamp(int(age_str.split(" ")[1]))
        comments_el = subline_el.select_one('a[href*="item?id="]')
        self.points = SoupUtils.extract_int_from_start(score_el.text)
        self.user = subline_el.find(class_="hnuser").text
        self.age = date
        self.comments = SoupUtils.extract_int_from_start(comments_el.text)

    def __str__(self):
        current_date = datetime.datetime.now()
        if self.age > current_date - datetime.timedelta(days=1):
            time_str = "today"
        elif self.age > current_date - datetime.timedelta(days=30):
            time_str = "on " + self.age.strftime("%Y-%m-%d")
        else:
            time_str = "over a month ago"
        comments_str = ""
        if self.comments < 100:
            comments_str = ""
        elif self.comments < 200:
            "(100+ comments - some engagement)"
        else:
            "(200+ comments - this news is generating very high engagement)"
        return f"""{self.title} (from {self.source} {time_str}) {comments_str}"""

class HackerNewsSouper():

    @staticmethod
    def get_hacker_news_items():
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = SoupUtils.get_soup("https://news.ycombinator.com")
        items = []
        main_table = SoupUtils.get_elements(class_path=[["tag", "table"]], parent=soup)[2]
        row_els = SoupUtils.get_elements(class_path=[["tag", "tr"]], parent=main_table)
        if len(row_els) < 10:
            raise Exception(f"Not enough news rows found!")

        hacker_news_item = None

        for el in row_els:
            if el.has_attr("id"):
                id = el.attrs["id"]
                if id != "pagespace":
                    titleline_el = el.find(class_="titleline")
                    if titleline_el is None:
                        Utils.log_yellow("Failed to get titleline_el for Hacker New items")
                    else:
                        try:
                            hacker_news_item = HackerNewsItem(id, titleline_el)
                        except Exception as e:
                            Utils.log_yellow(f"Failed to create Hacker News Item: {e}")
            else:
                subline_el = el.find(class_="subline")
                if subline_el is not None:
                    if hacker_news_item is None:
                        raise Exception("Hacker News Item not created yet!")
                    try:
                        hacker_news_item.update_for_subline(subline_el)
                        if hasattr(hacker_news_item, "id") and hacker_news_item.id is not None:
                            items.append(hacker_news_item)
                    except Exception as e:
                        Utils.log_red(el)
                        Utils.log_red("Failed to extract data for Hacker New items: " + str(e))
                hacker_news_item = None

        return items

    @staticmethod
    def get_nonblacklisted_stories(items=[]):
        headlines = []
        for item in items:
            blacklist_items = blacklist.test_all(item.title)
            if len(blacklist_items) > 0:
                Utils.log(f"item blacklisted: {item.title} ({blacklist_items})")
            else:
                headlines.append(item)
        return headlines

    @staticmethod
    def get_news(total=15):
        news_items = HackerNewsSouper.get_hacker_news_items()
        news_items = HackerNewsSouper.get_nonblacklisted_stories(news_items)
        if len(news_items) < 2:
            raise Exception("Not enough valid news found! Check log for blacklist reasons.")
        out = "Today's top stories from Hacker News:\n"
        counter = 0
        for item in news_items:
            if total > -1 and counter >= total:
                break
            counter += 1
            out += f"{item}\n"
        return out

if __name__ == "__main__":
    HackerNewsSouper.get_hacker_news_items()

