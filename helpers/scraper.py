import pandas as pd
import requests
from bs4 import BeautifulSoup

def _get_soup(url, verbose=False):
    response = requests.get(url)

    if verbose:
        print("Status code: ", response.status_code)

    html = response.text

    soup = BeautifulSoup(html, 'lxml')

    return soup

def _get_text_excluding_links(div):
    # Remove all <a> tags first
    for a in div.find_all("a"):
        a.decompose()
    # Now get the remaining text
    return div.get_text(strip=True)

def _get_heroes_and_winner(match):
    p1_div = match.find("div", {"class": "tournament-coverage__p1"})
    p2_div = match.find("div", {"class": "tournament-coverage__p2"})

    p1_hero = _get_text_excluding_links(p1_div.find("div", {"class": "tournament-coverage__player-hero-and-deck"}))
    p2_hero = _get_text_excluding_links(p2_div.find("div", {"class": "tournament-coverage__player-hero-and-deck"}))

    # Fuck DIO
    p1_hero = p1_hero.replace('/', '')
    p2_hero = p2_hero.replace('/', '')

    result = match.find("div", {"class": "tournament-coverage__result"}).get_text(strip=True)

    return (p1_hero, p2_hero, result)

def url_to_data_df(url, n_rounds):
    cc_rounds = [f"{url}results/{x}/" for x in range(1,n_rounds+1)]

    data_df = pd.DataFrame()
    for cc_round_url in cc_rounds:
        soup = _get_soup(cc_round_url)
        matches = soup.find_all("div", {"class" : "tournament-coverage__row--results"})
        for match in matches:
            p1, p2, result = _get_heroes_and_winner(match)

            # Bye
            if p1 == '' or p2 == '':
                continue
            
            if p1 not in data_df.columns:
                data_df[p1] = [(0, 0)] * len(data_df)
                data_df.loc[p1] = [(0, 0)] * len(data_df.columns)

            if p2 not in data_df.columns:
                data_df[p2] = [(0, 0)] * len(data_df)
                data_df.loc[p2] = [(0, 0)] * len(data_df.columns)

            if result == "◀Player 1Wins!▶":
                wins, draws = data_df.at[p1, p2]
                data_df.at[p1, p2] = (wins+1, draws)
            elif result == "◀Player 2Wins!▶":
                wins, draws = data_df.at[p2, p1]
                data_df.at[p2, p1] = (wins+1, draws)
            elif result == "◀Draw▶":
                wins, draws = data_df.at[p1, p2]
                data_df.at[p1, p2] = (wins, draws+1)

                wins, draws = data_df.at[p2, p1]
                data_df.at[p2, p1] = (wins, draws+1)
            else:
                raise ValueError

    data_df = data_df.sort_index(axis=0).sort_index(axis=1)
    return data_df

def data_df_to_ratio_df(data_df):
    ratio_df = pd.DataFrame(index=data_df.index, columns=data_df.columns)

    for row in data_df.index:
        for col in data_df.columns:
            wins, draws = data_df.at[row, col]
            loses = data_df.at[col, row][0]

            n_games = wins + draws + loses
            
            if row == col:
                ratio_df.at[row, col] = "M"
            elif n_games == 0:
                ratio_df.at[row, col] = "--"
            else:
                win_percentage = int((wins / n_games) * 100)
                ratio_df.at[row, col] = f"{win_percentage}%"

    return ratio_df

def data_df_to_hero_df(data_df, hero):
    hero_df = pd.DataFrame(columns=['Oponent Hero', '# Wins', '# Loses', '# Draws', '# Games', 'Winrate'])
 
    for opponent in data_df.columns:
        wins, draws = data_df.at[hero, opponent]
        loses = data_df.at[opponent, hero][0]

        n_games = wins + draws + loses

        if n_games == 0 or opponent == hero:
            continue
        
        winrate = int(wins/n_games * 100)

        hero_df.loc[len(hero_df)] = [opponent, wins, loses, draws, n_games, f'{winrate}%']

    return hero_df