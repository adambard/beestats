import re
import json
import os
import csv
import io
import pprint

from collections import defaultdict, OrderedDict

from ExtractTable import ExtractTable
from PIL import Image


# Init ET
et_session = ExtractTable(api_key=os.environ["EXTRACTTABLE_API_KEY"])
print(et_session.check_usage())


# Map peoples' various names to their canonical spreadsheet ones
PLAYER_NAMES = {
        # Elided for privacy
}


def prepare_image(filepath):
    """
    Crop a page 2 stats screenshot based on some proportions I worked out,
    save it, and return the filename of the cropped version
    """
    im = Image.open(filepath)
    print("Cropping", filepath, im.size)

    w, h = im.size
    left = int(w * 0.192)
    top = int(h * 0.083)
    bottom = h - int(h * 0.166)

    region = im.crop((left, top, w, bottom))
    cropped_filepath = filepath + ".cropped.png"
    region.save(cropped_filepath)

    return cropped_filepath


def load_image_data(filepath):
    """
    If we've previously sent this file to ExtractTable, use the cached version.
    Otherwise, do it (and cache the result).
    """

    print("Extracting text from", filepath)

    cache_file = filepath + ".json"
    if os.path.exists(cache_file):
        print("  Using cache")
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return data
        except FileNotFoundError:
            pass

    with open(cache_file, 'w') as f:
        print("  Making request")
        data = et_session.process_file(filepath=filepath, output_format="json")
        json.dump(data, f)
        return data


NUMS_RE = re.compile(r"[^\d.]")


def parsenum(s):
    """Turn a string into a number without making a fuss"""

    if not isinstance(s, str):
        return s

    s = NUMS_RE.sub("", s or "")
    if not s or s == "--":
        return 0

    if "." in s:
        return float(s)
    return int(s)


COLS_BY_IDX = {
    '0': "player_name",
    '1': "queen_kills",
    '2': "soldier_kills",
    '3': "drone_kills",
    '4': "deaths_as_queen",
    '5': "deaths_as_drone",
    '6': "dunks",
    '7': "swishes",
    '8': "miles",
    # The last two columns are stored as "gate_control", since they can be differentiated by role
    '9': "gate_control",
    '10': "gate_control"
}


def extract_data(raw_data):
    """
    Given the raw (and somewhat messy) data returned from ExtractTable, produce a
    more useful data structure of shape:

    >>> {
    >>>     "PlayerName": {
    >>>         "queen-kills": 1,
    >>>         "soldier_kills": 3,
    >>>         # ...
    >>>     },
    >>>     "PlayerName2": {
    >>>         #...
    >>>     },
    >>>     # ...
    >>> }

    """
    idx_by_player = {}
    pprint.pprint(raw_data)

    for idx, name in raw_data['0'].items():
        if not name:
            continue

        name = PLAYER_NAMES.get(name, name)
        idx_by_player[name] = idx

    sorted_players = sorted(idx_by_player.items(), key=lambda r: int(r[1]))
    data_by_player = OrderedDict([(player_name, {}) for player_name, _ in sorted_players])

    for colidx, col in raw_data.items():
        colname = COLS_BY_IDX.get(colidx, "?")
        for player_name, rowidx in idx_by_player.items():
            rowdata = col[rowidx]
            data_by_player[player_name][colname] = parsenum(rowdata)

    for idx, (pn, player_data) in enumerate(data_by_player.items()):
        player_data["gate_control"] = parsenum(player_data["gate_control"])
        player_data["role"] = "queen" if idx in [0, 4] else "worker"
        player_data["team"] = "Blue" if idx < 4 else "Gold"

    return data_by_player


def print_data(data):
    """
    Print the processed data in TSV format for easy copy/pasting into sheets
    """
    f = io.StringIO()
    w = csv.writer(f, delimiter="\t")

    w.writerow(["Team", "Name", "Role", "Queen Kills", "Soldier Kills", "Drone Kills", "Total Deaths", "Miles", "Dunks", "Swishes", "Gate Control %", "Soldier %"])

    for player_name, row in data.items():
        w.writerow([
            row["team"],
            player_name,
            row["role"],
            row["queen_kills"],
            row["soldier_kills"],
            row["drone_kills"],
            row["deaths_as_queen"] + row["deaths_as_drone"],
            row["miles"],
            row["dunks"],
            row["swishes"],
            row["gate_control"] if row["role"] == "queen" else "",
            row["gate_control"] if row["role"] == "worker" else ""
        ])

    print(f.getvalue())


def parse_img(filepath):
    """
    Main entrypoint to prepare, parse, process, and print the stats from a result image
    """
    cropped_filepath = prepare_image(filepath)
    datas = load_image_data(cropped_filepath)
    for d in datas:
        d = extract_data(json.loads(d))
        print_data(d)


if __name__ == "__main__":
    for path in os.listdir("./apr5"):
        if "cropped" in path:
            continue
        if path.endswith(".jpg") or path.endswith(".png"):
            fullpath = "./apr5/" + path
            parse_img(fullpath)
