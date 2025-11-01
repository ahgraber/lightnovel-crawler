import logging
import os
import re
from typing import Generator

from bs4 import BeautifulSoup

from ..assets.chars import Chars

logger = logging.getLogger(__name__)


def make_texts(app, data) -> Generator[str, None, None]:
    from ..core.app import App

    assert isinstance(app, App) and app.crawler

    for vol in data:
        dir_name = os.path.join(app.output_path, "text", vol)
        os.makedirs(dir_name, exist_ok=True)
        for chap in data[vol]:
            with app.use_chapter_body(chap) as body:
                if not body:
                    continue
                file_name = "%s.txt" % str(chap["id"]).rjust(5, "0")
                file_name = os.path.join(dir_name, file_name)
                with open(file_name, "w", encoding="utf8") as file:
                    formatted = body.replace("</p><p", "</p>\n<p")
                    soup = BeautifulSoup(formatted, "lxml")
                    text = "\n\n".join(soup.stripped_strings)
                    text = re.sub(r"[\r\n]+", Chars.EOL + Chars.EOL, text)
                    file.write(text)
                    yield file_name
