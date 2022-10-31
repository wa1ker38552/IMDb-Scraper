from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from bs4 import BeautifulSoup
import requests
import json

'''
https://www.imdb.com/event/all/?ref_=nv_ev_all
Scrape all the events like oscars, the event details 
all categories recent nominees winners, movie info
production crew, full credit details

save files into json by year and the award events name
'''


class Scraper:
  def __init__(self, path='data.json'):
    self.path = path
    self.client = requests.Session()
    self.events = self.find_events()

    # initialize webdriver to render javascript
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('disable-infobars')
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_experimental_option("excludeSwitches",["enable-automation"])
    self.driver = webdriver.Chrome(options=chrome_options)
    self.driver.maximize_window()

  def find_events(self):
    request = self.client.get('https://d2vyvawkvp20f9.cloudfront.net/event/index/data.json')
    return request.json()

  def fetch_event(self, event):
    data = json.loads(open(self.path, 'r').read())
    self.driver.get(f'https://www.imdb.com/event/{event["id"]}')
    soup = BeautifulSoup(self.driver.page_source, 'html.parser')

    # get event name and year
    try:
      year = soup.find('div', attrs={'class': 'event-year-header__year'}).get_text()
      format_year = year.replace(' Awards', '')
    except AttributeError:
      # can't find award year
      year, format_year = None, None

      
    # get event history
    history = soup.find_all('div', attrs={'class': 'event-history-widget__years-row'})
    history = ''.join([x.get_text() for x in history])
    c, years = 0, []
    for i in range(int(len(history)/4)): 
      years.append(history[c:c+4])
      c+=4

    if year is None and format_year is None:
      year = f'{years[0]} Awards'
      format_year = years[0]

    # categorize by year
    if not format_year in data:
      data[format_year] = {}
    data[format_year][f'{event["name"]}, {year}'] = {'categories': {}, 'year': format_year, 'event_history': years}
    
    # get categories
    awards = soup.find_all('div', attrs={'class': 'event-widgets__award-category-name'})
    awards = [award.get_text() for award in awards]

    # collect nominees within an category
    nominees = soup.find_all('div', attrs={'class': 'event-widgets__award-category-nominations'})

    # get award title instead of category
    if len(nominees) != len(awards):
      awards = soup.find_all('div', attrs={'class': 'event-widgets__award-name'})
      awards = [award.get_text() for award in awards]
    
    # more differences
    if len(nominees) != len(awards) and len(awards) == 1:
      nominees = [''.join([str(n) for n in nominees])]
      
    for i, nom in enumerate(nominees):
      print(f'- {awards[i]}')
      data[format_year][f'{event["name"]}, {year}']['categories'][awards[i]] = []
      search = BeautifulSoup(str(nom), 'html.parser')

      # check if it could find them
      names = search.find_all('div', attrs={'class': 'event-widgets__primary-nominees'})
      raw_films = [n.get_text().replace(' (actor)', '').replace(' (actress)', '') for n in names]

      # check if contains multiple actors/actresses
      if ',' in raw_films[0]: raw_films = [x.strip() for x in raw_films[0].split(',')]
      
      n = search.find_all('span', attrs={'class': 'event-widgets__nominee-name'})
      
      # search for id's within title
      category_ids = []
      category_names = []
      category_types = []
      for title in n:
        search = BeautifulSoup(str(title), 'html.parser')
        raw_href = search.find('a')
        raw_name = search.find('a').get_text()
        if raw_name in raw_films and not raw_name in category_names:
          id = str(raw_href).split('/')[2]
          category_ids.append(id)
          category_names.append(raw_name)

          # check if it's a name
          if 'name' in str(raw_href):
            category_types.append('person')
          else:
            category_types.append('title')

      for x in range(len(category_ids)):
        data[format_year][f'{event["name"]}, {year}']['categories'][awards[i]].append({
          'name': category_names[x],
          'id': category_ids[x],
          'type': category_types[x]
        })

    # query movies
    for cat in data[format_year][f'{event["name"]}, {year}']['categories']:
      movies = data[format_year][f'{event["name"]}, {year}']['categories'][cat]
      for i, mov in enumerate(movies):
        if mov['type'] == 'person':
          request = self.client.get(f'https://www.imdb.com/name/{mov["id"]}')
          soup = BeautifulSoup(request.text, 'html.parser')

          # find and set bio
          bio = soup.find('div', attrs={'class': 'name-trivia-bio-text'})
          data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['bio'] = bio.get_text()

          nom_raw = soup.find('span', attrs={'class': 'awards-blurb'})
          nom_raw_init = nom_raw.get_text().strip()

          # if user has an oscar, it shows as the second awards-blurb
          if 'oscar' in nom_raw_init.lower():
            nom_raw = soup.find_all('span', attrs={'class': 'awards-blurb'})[1]
            nom_raw_init = nom_raw.get_text().strip()

          # handle different events
          nom_raw = nom_raw_init.replace('\n', '').replace('wins & ', '').replace('win & ', '').replace(' nominations.', '').replace(' nomination.', '').replace('win.', '').replace('wins.', '').replace('Another ', '').split()
          if len(nom_raw) == 1 and 'nomination' in nom_raw_init:
            data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': 0, 'nominations': int(nom_raw[0])}
          elif len(nom_raw) == 1 and 'win' in nom_raw_init:
            data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': int(nom_raw[0]), 'nominations': 0}
          else:
            data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': int(nom_raw[0]), 'nominations': int(nom_raw[1])}

          # get 'known for' movies
          data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['known_for'] = {} 
          known_raw = soup.find_all('div', attrs={'class': 'knownfor-title'})
          for item in known_raw:
            search = BeautifulSoup(str(item), 'html.parser')
            title = search.find('a', attrs={'class': 'knownfor-ellipsis'}).get_text()
            role = search.find('span', attrs={'class': 'knownfor-ellipsis'}).get_text()
            
            # can't reuse year variable
            yr = search.find('div', attrs={'class', 'knownfor-year'}).get_text()
            data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['known_for'][title] = {'role': role, 'year': yr.replace('(', '').replace(')', '')}
            
        else:
          # process movie
          request = self.client.get(f'https://www.imdb.com/title/{mov["id"]}/?ref_=ev_nom')
          soup = BeautifulSoup(request.text, 'html.parser')

          try:
            description = soup.find('span', attrs={'class': 'sc-16ede01-2 gXUyNh'}).get_text()
          except AttributeError: description = None
          try:
            rating = soup.find('span', attrs={'class': 'sc-7ab21ed2-1 jGRxWM'}).get_text()
          except AttributeError:
            # no ratings for movie
            rating = 0
          
          dat = soup.find('ul', attrs={'class': 'ipc-metadata-list ipc-metadata-list--dividers-all title-pc-list ipc-metadata-list--baseAlt'})
          search = BeautifulSoup(str(dat), 'html.parser')
          users = search.find_all('li', attrs={'class': 'ipc-metadata-list__item'})

          cast = []
          for type in users:
            search = BeautifulSoup(str(type), 'html.parser')
            names = search.find_all('li', attrs={'class': 'ipc-inline-list__item'})

            for n in names:
              id = str(n).split('href')[1].split('/')[2]
              name = n.get_text()

              cast_data = {
                'name': name,
                'id': id
              }
              if not cast_data in cast: cast.append(cast_data)
            data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['cast'] = cast

          data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['rating'] = float(rating)
          data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['description'] = description
          
          with open(self.path, 'w') as file:
            file.write(json.dumps(data, indent=2))
      

scraper = Scraper()

'''
for i in range(0, 20):
  print(f'-- {i}. {scraper.events[i]["name"]}')
  scraper.fetch_event(scraper.events[i])
'''
scraper.fetch_event(scraper.events[149])
