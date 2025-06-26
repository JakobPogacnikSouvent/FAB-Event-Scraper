from flask import Flask, request, render_template, send_file, session, redirect
import uuid
import pandas as pd
from io import BytesIO
from flask_caching import Cache
import re
import io
from openpyxl.styles import Alignment

from helpers.scraper import *

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Needed for sessions
cache = Cache(app, config={
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 3600
})

@app.before_request
def set_user_id():
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())

def get_last_segment(url: str) -> str | None:
    """
    Returns the segment between the last two slashes of the URL.
    If there's no trailing slash, it'll still capture the final segment.
    """
    pattern = re.compile(r"(?<=\/)[^\/]+(?=(?:\/)?$)")
    match = pattern.search(url)
    return match.group(0) if match else None

def is_valid_fab_url(url: str) -> bool:
    pattern = r"^https://fabtcg\.com/en/coverage/.+/$"
    return bool(re.match(pattern, url))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form["url"]
        n_rounds = int(request.form["n_rounds"])
        # url = "https://fabtcg.com/en/coverage/battle-hardened-las-vegas-2025/"
        # n_rounds = 9

        if not is_valid_fab_url(url):
            return render_template('index.html', error_message="Invalid URL.")
        
        event_name = f"{get_last_segment(url).replace("-", " ").title()}, Rounds 1-{n_rounds}"


        try:
            data_df = url_to_data_df(url, n_rounds)
        except Exception as e:
            return render_template('index.html', error_message=f"Error occured during data scraping:\n{e}")
        
        cache.set(f"data_df:{session['user_id']}", data_df)
        cache.set(f"event_name:{session['user_id']}", event_name)


        return redirect("/matchup_results")

        
        # ratio_df = make_index_clickable(ratio_df)
        # table_html = ratio_df.to_html(classes="dataframe", escape=False)
        # return render_template("show.html", table=table_html)

    return render_template("index.html")

def make_index_clickable(df):
    # Create a new column for index links
    df = df.copy()
    df.index = df.index.map(lambda x: f'<a class="fab-navbar-link" href="/hero_matchups/{x}">{x}</a>')
    return df

def make_opponent_hero_clickable(df):
    df = df.copy()
    df['Oponent Hero'] = df['Oponent Hero'].map(lambda x: f'<a class="fab-navbar-link" href="/hero_matchups/{x}">{x}</a>')
    return df
    
def highlight_cells(val):
    def lerp_color(c1, c2, t):
        # Linear interpolate between two RGB colors c1 and c2 by factor t (0 <= t <= 1)
        return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

    if isinstance(val, str):
        val = val.strip()
        if val == "M":
            return "background-color: rgba(161, 208, 242, 0.75); color: black;"
        elif val == "--":
            return "color: black;"
        elif val.endswith("%"):
            try:
                pct = float(val.rstrip("%"))
                pct = max(0, min(100, pct))  # clamp pct between 0 and 100

                red = (231, 25, 31)
                yellow = (222, 202, 61)
                green = (150, 188, 77)

                if pct <= 50:
                    # interpolate between red and yellow
                    t = pct / 50
                    rgb = lerp_color(red, yellow, t)
                else:
                    # interpolate between yellow and green
                    t = (pct - 50) / 50
                    rgb = lerp_color(yellow, green, t)

                return f"background-color: rgb{rgb}; color: black;"
            except ValueError:
                pass
    return ""



@app.route("/matchup_results", methods=["GET", "POST"])
def show_matchup_results():
    data_df = cache.get(f"data_df:{session['user_id']}")
    event_name = cache.get(f"event_name:{session['user_id']}")
    if data_df is None or event_name is None:
        return redirect("/")

    ratio_df = data_df_to_ratio_df(data_df)
    ratio_df = make_index_clickable(ratio_df)
    
    styled_df = ratio_df.style.applymap(highlight_cells)
    table_html = styled_df.set_table_attributes('class="dataframe"').to_html()

    table_title = f"{event_name} : Matchup Results"
    return render_template("matchup_results.html", table=table_html, table_title=table_title)

@app.route("/hero_matchups/<hero_name>")
def show_row(hero_name):
    data_df = cache.get(f"data_df:{session['user_id']}")
    event_name = cache.get(f"event_name:{session['user_id']}")
    if data_df is None:
        return redirect("/")

    hero_df = data_df_to_hero_df(data_df, hero_name)
    hero_df = make_opponent_hero_clickable(hero_df)
    # table_html = hero_df.to_html(classes="dataframe", escape=False, index=False)

    styled_df = hero_df.style.applymap(highlight_cells, subset=["Winrate"])

    table_html = styled_df.set_table_attributes('class="hero-dataframe"').hide(axis="index").to_html()

    table_title = f"{event_name} : {hero_name}"
    return render_template("hero_matchups.html", table=table_html, table_title=table_title)

@app.route("/download_csv")
def download_csv():
    data_df = cache.get(f"data_df:{session['user_id']}")
    event_name = cache.get(f"event_name:{session['user_id']}")
    if data_df is None or event_name is None:
        return redirect("/")

    ratio_df = data_df_to_ratio_df(data_df)
    hero_dataframes = [(hero, data_df_to_hero_df(data_df, hero)) for hero in data_df.index]

    output = io.BytesIO()
    invalid_chars = r'[:\\/*?\[\]]'

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Save ratio_df WITH index
        ratio_df.to_excel(writer, sheet_name="Matchup Results", index=True)

        # Save hero dataframes WITHOUT index
        for hero_name, hero_df in hero_dataframes:
            clean_name = re.sub(invalid_chars, '', hero_name)
            hero_df.to_excel(writer, sheet_name=clean_name, index=False)

        # Access the workbook and worksheet for ratio_df to style columns
        workbook = writer.book
        worksheet = writer.sheets["Matchup Results"]

        # Rotate column headers vertically (angle=90)
        # Headers start from row 1 (Excel 1-based) and column 2 (because col A is index)
        for col_idx in range(2, 2 + len(ratio_df.columns)):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.alignment = Alignment(textRotation=90, horizontal='center', vertical='bottom')

    output.seek(0)

    return send_file(
        output,
        download_name=f"{event_name}_data.xlsx",
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


if __name__ == "__main__":
    app.run()
