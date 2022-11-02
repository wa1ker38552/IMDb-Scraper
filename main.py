from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from bs4 import BeautifulSoup
from threading import Thread
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

    # save events to file
    with open('self.data.txt', 'w') as file: 
      file.write('\n'.join([i['name'] for i in self.events]))

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

  def fetch_event(self, event, year=None):
    self.data = json.loads(open(self.path, 'r').read())

    if year is None:
      self.driver.get(f'https://www.imdb.com/event/{event["id"]}')
    else:
      self.driver.get(f'https://www.imdb.com/event/{event["id"]}/{year}')
    
    soup = BeautifulSoup(self.driver.page_source, 'html.parser')

    # get event name and year
    try:
      year = soup.find('div', attrs={'class': 'event-year-header__year'}).get_text()
      format_year = year.replace(' Awards', '')
    except AttributeError:
      # can't find award year
      year, format_year = None, None

    # location
    location = soup.find('div', attrs={'class': 'event-header__subtitle'})
    try:
      location = location.get_text()
    except AttributeError: pass
      
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
    if not format_year in self.data:
      self.data[format_year] = {}
    self.data[format_year][f'{event["name"]}, {year}'] = {'categories': {}, 'year': format_year, 'event_history': years, 'location': location}
    
    # get categories
    awards = soup.find_all('div', attrs={'class': 'event-widgets__award-category-name'})
    awards = [award.get_text() for award in awards]

    # collect nominees within an category
    nominees = soup.find_all('div', attrs={'class': 'event-widgets__award-category-nominations'})

    cat = soup.find_all('div', attrs={'class': 'event-widgets__award-name'})
    if len(nominees)-len(awards) == len(cat)-1:
      nominees = nominees[:len(awards)]
      
    # get award title instead of category
    if len(nominees) != len(awards):
      nominees = soup.find_all('div', attrs={'class': 'event-widgets__award'})
      awards = soup.find_all('div', attrs={'class': 'event-widgets__award-name'})
      awards = [award.get_text() for award in awards]

    # more differences
    elif len(nominees) != len(awards) and len(awards) == 1:
      nominees = [''.join([str(n) for n in nominees])]

    for i, nom in enumerate(nominees):
      print(f'- {awards[i]}')
      self.data[format_year][f'{event["name"]}, {year}']['categories'][awards[i]] = []
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
        self.data[format_year][f'{event["name"]}, {year}']['categories'][awards[i]].append({
          'name': category_names[x],
          'id': category_ids[x],
          'type': category_types[x]
        })

    with open(self.path, 'w') as file:
        file.write(json.dumps(self.data, indent=2))
      
    # query movies
    for cat in self.data[format_year][f'{event["name"]}, {year}']['categories']:
      print('Searching category')
      Thread(target=lambda: self.search_category(format_year, event, year, cat)).start()

  def search_category(self, format_year, event, year, cat):
    movies = self.data[format_year][f'{event["name"]}, {year}']['categories'][cat]
    for i, mov in enumerate(movies):
      print(f'{i}/{len(movies)}')
      if mov['type'] == 'person':
        request = self.client.get(f'https://www.imdb.com/name/{mov["id"]}')
        soup = BeautifulSoup(request.text, 'html.parser')

        # find and set bio
        bio = soup.find('div', attrs={'class': 'name-trivia-bio-text'})
        self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['bio'] = bio.get_text()

        nom_raw = soup.find('span', attrs={'class': 'awards-blurb'})
        nom_raw_init = nom_raw.get_text().strip()

        # if user has an oscar, it shows as the second awards-blurb
        if 'oscar' in nom_raw_init.lower() or 'emmy' in nom_raw_init.lower() or 'bafta' in nom_raw_init.lower():
          nom_raw = soup.find_all('span', attrs={'class': 'awards-blurb'})[1]
          nom_raw_init = nom_raw.get_text().strip()

        # handle different events
        nom_raw = nom_raw_init.replace('\n', '').replace('wins & ', '').replace('win & ', '').replace(' nominations.', '').replace(' nomination.', '').replace('win.', '').replace('wins.', '').replace('Another ', '').split()
        try:
          if len(nom_raw) == 1 and 'nomination' in nom_raw_init:
            self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': 0, 'nominations': int(nom_raw[0])}
          elif len(nom_raw) == 1 and 'win' in nom_raw_init:
            self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': int(nom_raw[0]), 'nominations': 0}
          else:
            self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['awards'] = {'wins': int(nom_raw[0]), 'nominations': int(nom_raw[1])}
        except ValueError:
          print(mov['id'])
          print(nom_raw, nom_raw_init)
            
        # get 'known for' movies
        self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['known_for'] = {} 
        known_raw = soup.find_all('div', attrs={'class': 'knownfor-title'})
        for item in known_raw:
          search = BeautifulSoup(str(item), 'html.parser')
          title = search.find('a', attrs={'class': 'knownfor-ellipsis'}).get_text()
          role = search.find('span', attrs={'class': 'knownfor-ellipsis'}).get_text()
          
          # can't reuse year variable
          yr = search.find('div', attrs={'class', 'knownfor-year'}).get_text()
          self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['known_for'][title] = {'role': role, 'year': yr.replace('(', '').replace(')', '')}
          
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
        
        dat = soup.find('ul', attrs={'class': 'ipc-metaself.data-list ipc-metaself.data-list--dividers-all title-pc-list ipc-metaself.data-list--baseAlt'})
        search = BeautifulSoup(str(dat), 'html.parser')
        users = search.find_all('li', attrs={'class': 'ipc-metaself.data-list__item'})

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
          self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['cast'] = cast

        self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['rating'] = float(rating)
        self.data[format_year][f'{event["name"]}, {year}']['categories'][cat][i]['description'] = description
        
      with open(self.path, 'w') as file:
        file.write(json.dumps(self.data, indent=2))
      

scraper = Scraper()

'''
for i in range(0, 20):
  print(f'-- {i}. {scraper.events[i]["name"]}')
  scraper.fetch_event(scraper.events[i])
'''
# scraper.fetch_event(scraper.events[150])


# with open('self.data.txt', 'w') as file: file.write('\n'.join([i['name'] for i in scraper.events]))

# years = json.loads(open('self.data.json', 'r').read()) ['2022']['Cannes Film Festival, 2022 Awards']['event_history']
# for yr in years[1:10]:
  # scraper.fetch_event(scraper.events[1444], year=yr)

# scraper.fetch_event(scraper.events[0])

scraper.fetch_event(scraper.events[4208])
