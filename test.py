import requests

#lines = requests.get("https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds?regions=us&markets=h2h,spreads,totals&oddsFormat=american&date=2021-10-18T12:00:00Z&apiKey=ee5b562ccf34ae609d640605eb3f4067")

#for x in lines.json():
#    print(x["home_team"], "vs", x["away_team"], "@", x["commence_time"])


#with open("odds.json", "w") as f:
#    f.write(lines.text)

scores = requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week=1") 

with open("data/week1.json", "w") as f:
    f.write(scores.text)