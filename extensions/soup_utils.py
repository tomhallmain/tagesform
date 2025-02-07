import html
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
import pandas as pd
import io
import re

from utils.utils import Utils


class WebConnectionException(Exception):
    """Raised on failure to connect HTML"""
    pass


class SoupUtils:
    @staticmethod
    def remove_tags(html_string):
        return re.sub('<[^<]+?>', '', html_string).strip()

    @staticmethod
    def clean_html(html_encoded):
        return urllib.parse.unquote(html.unescape(html_encoded))

    @staticmethod
    def get_soup(url=None, base_url="", extension=""):
        if url is None:
            url = f"{base_url}{extension}"
        try:
            response = urllib.request.urlopen(url)
            html_string = response.read().decode("utf-8")
            soup = BeautifulSoup(html_string, "lxml")
            return soup
        except Exception as e:
            raise WebConnectionException(f"Failed to get HTML for {url}: {e}")

    @staticmethod
    def get_elements(class_path=[["class","*"]], parent=None):
        assert parent is not None
        all_elements = []
        type_def = class_path[0]
        _type = type_def[0]
        value = type_def[1]
        
        lowest_class = len(class_path) == 1

        if _type == "class":
            elements = parent.find_all(class_=value)
        elif _type == "id":
            elements = parent.find_all(id=value)
        elif _type == "tag":
            elements = parent.find_all(value)
        else:
            raise Exception("Unhandled type: " + _type)

        # Utils.log(f"Found {len(elements)} elements of {_type}={value}")
        
        if lowest_class:
            all_elements = elements
        else:
            for element in elements:
                all_elements.extend(SoupUtils.get_elements(class_path[1:], element))

        return all_elements

    @staticmethod
    def get_element_texts(class_path=[["class","*"]], start_element=None):
        out = []
        try:
            for element in SoupUtils.get_elements(class_path, start_element):
                out.append(element.text)
        except Exception as e:
            Utils.log_yellow(f"Failed to find elements of class {class_path} - {e}")
        return out

    @staticmethod
    def extract_int_from_start(s):
        out = ""
        for c in s:
            if c.isdigit():
                out += c
            else:
                break
        return int(out)

    @staticmethod
    def get_table_data(table_el):
        return pd.read_html(io.StringIO(str(table_el)))[0]

    @staticmethod
    def get_links(soup):
        links  = []
        for link in soup.find_all('a'):
            if 'href' in link.attrs:
                links.append(link['href'])
        return links

