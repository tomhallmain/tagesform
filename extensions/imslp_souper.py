import io
import json
import os
import pandas as pd
import time

from extensions.soup_utils import SoupUtils
from utils.utils import Utils


def clean_wiki_text(text):
    if text is None or type(text) != str:
        return text
    text = text.strip()
    if text.endswith(']') and "[" in text:
        text = text[:text.index("[")]
    return SoupUtils.clean_html(text)


class ImslpTable():
    def __init__(self, table=None):
        if table is None:
            self.df = pd.DataFrame()
        elif type(table) == pd.DataFrame:
            self.df = table
        else:
            self.df = SoupUtils.get_table_data(table)
        self.clean_df()

    def clean_df(self):
        for col in self.df:
            self.df[col] = self.df[col].apply(lambda x: clean_wiki_text(x))

    def has_data(self):
        return len(self.df) != 0

    def get_rows(self):
        return self.df.values.tolist()
    
    def get_single_line_row_value(self, row=0, col=1):
        return self.df.iat[row, col]

    def is_invalid_table(self):
        rows = self.get_rows()
        if len(rows) == 0:
            return True
        first_row = rows[0]
        if len(first_row) > 0:
            maybe_header_table_value = first_row[0]
            if maybe_header_table_value is not None: 
                if maybe_header_table_value.startswith("This list is manually maintained"):
                    return True
        if len(first_row) > 1:
            maybe_header_table_value = first_row[1]
            if maybe_header_table_value is not None and type(maybe_header_table_value) == str:
                if maybe_header_table_value.startswith("This section"):
                    return True
                if maybe_header_table_value.startswith("This article"):
                    return True
                if maybe_header_table_value.startswith("You can help"):
                    return True
        return False

    @staticmethod
    def from_json(json):
        return pd.read_json(io.StringIO(json))

    def __str__(self):
        return str(self.df)


class ImslpSection():
    def __init__(self, header, tables=[]):
        self._header = header if type(header) == str else header.text
        if self._header and self._header.strip().endswith("]") and "[" in self._header:
            self._header = self._header[:self._header.index("[")]
        if self._header:
            self._header = clean_wiki_text(self._header)
        self._table_temp = None
        self._tables = []
        for table in tables:
            self._tables.append(ImslpTable(table))

    def add_table(self, table):
        self._tables.append(ImslpTable(table))

    def add_table_part(self, p):
        if self._table_temp is None:
            self._table_temp = pd.DataFrame()
        self._table_temp = self._table_temp._append(pd.DataFrame([p.text.strip()]))

    def combine_temp_table(self):
        if self._table_temp is not None and len(self._table_temp) > 0:
            self._table_temp.reset_index(drop=True, inplace=True)
            self._tables.append(ImslpTable(self._table_temp))
            self._table_temp = None

    def has_data(self):
        for table in self._tables:
            if table.has_data():
                return True
        return False

    def verify_cleanliness(self):
        cleanliness_types = set()
        for table in self._tables:
            if table.is_invalid_table():
                # Utils.log(self._header + " - Table is invalid")
                cleanliness_types.add(2)
                continue
            rows = table.get_rows()
            if len(rows) < 4:
                # Utils.log(self._header + " - Table is too small: \n" + str(rows))
                cleanliness_types.add(1)
                continue
            cleanliness_types.add(0)
        return sorted(list(cleanliness_types))

    def json(self):
        return {
            "header": self._header,
            "tables": [
                table.df.to_json() for table in self._tables
            ]
        }

    @staticmethod
    def from_json(data):
        return ImslpSection(data["header"], [ImslpTable.from_json(t) for t in data["tables"]])

    def __str__(self):
        out = self._header + '\n'
        for table in self._tables:
            out += str(table) + '\n'
        return out


class ImslpCompilationData:
    SAVE_LOCATION = os.path.join(os.path.dirname(os.path.dirname(__file__)), "library_data", "wiki")

    def __init__(self, url, has_tables):
        self._url = url
        last_part_of_url = url[url.rfind("/")+1:]
        self._name = clean_wiki_text(last_part_of_url.replace("_", " ").replace(":", "_") + " (IMSLP)")
        if "/" in self._name:
            raise Exception("Compilation name contains '/'")
        self._sections = []
        self._has_tables = has_tables

    def add_section(self, section_el):
        section = ImslpSection(section_el)
        self._sections.append(section)
        return section

    def has_section(self, section):
        for s in self._sections:
            if s == section or (s is not None and s.header() == section.header()):
                return True
        return False

    def has_data(self):
        for section in self._sections:
            if section.has_data():
                return True
        return False

    def verify_cleanliness(self):
        cleanliness_types = set()
        for section in self._sections:
            scores = section.verify_cleanliness()
            for score in scores:
                cleanliness_types.add(score)
        return sorted(list(cleanliness_types))

    def json(self):
        return {
            'url': self._url,
            'name': self._name,
            'sections': [section.json() for section in self._sections]
            }

    def save_to_file(self):
        filename = os.path.join(ImslpCompilationData.SAVE_LOCATION, self._name + ".json")
        with open(filename, 'w', encoding="utf-8") as f:
            f.write(json.dumps(self.json(), indent=4))

    @staticmethod
    def load_from_file(name):
        with open(name, 'r', encoding="utf-8") as f:
            data = json.loads(f.read())
            wiki_compilation_data = ImslpCompilationData(data['url'], None)
            for section in data['sections']:
                wiki_compilation_data._sections.append(ImslpSection.from_json(section))
        return wiki_compilation_data


class ImslpSouper():

    @staticmethod
    def get_wiki_main_content(soup):
        main = soup.find('main', {'id:': 'content'})
        return main

    @staticmethod
    def get_wiki_body_content(soup):
        body = soup.find('div', {'class': 'body'})
        return body

    @staticmethod
    def get_catlinks(soup):
        catlinks = soup.find('div', {'id': 'catlinks'})
        return catlinks

    @staticmethod
    def extract_table_data(el, section, wiki_compilation_data, depth=0):
        if el.name == 'table' and wiki_compilation_data._has_tables:
            section.add_table(el)
        if depth == 0 and el.name == 'p' and not wiki_compilation_data._has_tables:
            section.add_table_part(el)
        if el.name == 'ul' or el.name == 'ol':
            for li in el.contents:
                if li.name == 'li':
                    section.add_table_part(li)
            section.combine_temp_table()
        if el.name == 'dl':
            if el.contents[0].name == 'dd':
                for dd in el.contents:
                    if dd.name == 'dd':
                        sub_dl = dd.find('dl')
                        if sub_dl is not None and len(sub_dl.contents[0]) > 1:
                            for dd1 in sub_dl.contents:
                                if dd1.name == 'dd':
                                    section.add_table_part(dd1)
                        else:
                            section.add_table_part(dd)
                section.combine_temp_table()
            else:
                for dd in el.contents[0]:
                    if dd.name == 'dd':
                        sub_dl = dd.find('dl')
                        if sub_dl is not None and len(sub_dl.contents[0]) > 1:
                            for dd1 in sub_dl.contents:
                                if dd1.name == 'dd':
                                    section.add_table_part(dd1)
                        else:
                            section.add_table_part(dd)
                section.combine_temp_table()
        if el.name == 'div' and depth < 3:
            for sub_el in el.contents:
                ImslpSouper.extract_table_data(sub_el, section, wiki_compilation_data, depth=depth+1)

    @staticmethod
    def get_wiki_tables(wiki_url):
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = SoupUtils.get_soup(wiki_url)
        body_content = ImslpSouper.get_wiki_body_content(soup)
        tables = SoupUtils.get_elements(class_path=[["tag", "table"]], parent=body_content)
        # catlinks = WikiSouper.get_catlinks(soup)
        has_tables = len(tables) > 0
        wiki_compilation_data = ImslpCompilationData(wiki_url, has_tables)
        section = ImslpSection(wiki_compilation_data._name)

        for el in body_content.contents:
            if el.name == 'div' and el.has_attr('class') and len(el['class']) > 0 and el['class'][0] == 'mw-heading':
                if section is not None:
                    if section.has_data() or section._header != wiki_compilation_data._name:
                        section.combine_temp_table()
                        wiki_compilation_data._sections.append(section)
                header = el.contents[0]
                if header.attrs['id'] == 'References':
                    break
                section = wiki_compilation_data.add_section(el)
            if section is not None:
                ImslpSouper.extract_table_data(el, section, wiki_compilation_data)

        if section is not None:
            section.combine_temp_table()
            if not wiki_compilation_data.has_section(section):
                wiki_compilation_data._sections.append(section)

        for section in wiki_compilation_data._sections:
            Utils.log(section)

        return wiki_compilation_data

    @staticmethod
    def save_to_files(wiki_urls=[]):
        invalid_data_urls = []
        failed_urls = {}
        for wiki_url in wiki_urls:
            try:
                wiki_compilation_data = ImslpSouper.get_wiki_tables(wiki_url)
                wiki_compilation_data.save_to_file()
                if not wiki_compilation_data.has_data():
                    invalid_data_urls.append(wiki_url)
            except Exception as e:
                Utils.log("Error gathering data from Wiki url: " + wiki_url)
                Utils.log_red(e)
                failed_urls[wiki_url] = str(e)
                # raise e
            Utils.log("\n-----------------------------------------------------------\n")
            time.sleep(2)
        
        if len(invalid_data_urls) > 0:
            Utils.log_yellow("Invalid data urls:")
            for url in invalid_data_urls:
                Utils.log_yellow(url)

            Utils.log("\n-----------------------------------------------------------\n")

        if len(failed_urls) > 0:
            Utils.log_red("Failed urls: ")
            for url, e in failed_urls:
                Utils.log_red(f"{url} - {e}")



