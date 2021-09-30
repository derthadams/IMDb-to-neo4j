from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from neo4j import GraphDatabase, basic_auth
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json
import html as h
import config

IMDB_SIGNIN_URL = 'https://www.imdb.com/registration/signin'
IMDB_NAME_BASE_URL = 'https://www.imdb.com/name/'
IMDB_TITLE_BASE_URL = 'https://www.imdb.com/title/'

def get_json(soup):
    data = soup.select_one('script[type="application/ld+json"]')
    if data:
        return json.loads(data.text)
    else:
        return None


class Page(object):
    def __init__(self, driver, imdb_id):
        """
        driver [Selenium driver object]     Selenium driver
        url [string]                        URL of the page
        """
        self.driver = driver
        self.imdb_id = imdb_id

    def _get_page(self, url):
        j = 5
        while j > 0:
            try:
                self.driver.get(url)
                self.soup = BeautifulSoup(self.driver.page_source,
                                          'html.parser')
                break
            except TimeoutException:
                self.driver.refresh()
                j -= 1


class NamePage(Page):
    def __init__(self, driver, session, crew):
        """
        :param driver:      Selenium driver object
        :param session:     neo4j session
        :param crew:        Person object
        """
        Page.__init__(self, driver, crew.imdb_name_id)
        self.url = IMDB_NAME_BASE_URL + self.imdb_id + '/'
        self._get_page(self.url)
        self.name = get_json(self.soup)['name']
        self._get_credits(session)

    def _get_credits(self, session):
        self.credit_list = []
        self.div_list = self.soup.findAll('div', {'class': {'filmo-row even',
                                                            'filmo-row odd'}})
        for div in self.div_list:
            self.credit_list.append(Credit(div, self.driver, session))

    def __iter__(self):
        return iter(self.credit_list)


class Person(object):
    def __init__(self, imdb_name_id, full_name):
        """imdbNameID:  [string]    imdbNameID of the person
           fullName:    [string]    person's full name"""
        self.imdb_name_id = imdb_name_id
        self.full_name = full_name


class Credit(object):
    """ DATA MEMBERS
        div             div containing information for a single screen credit
        driver          selenium driver
        session         neo4j session
        title           [string]    show title
        imdb_title_id   [string]    show imdb title id
        show_type       [string]    show type ie, 'Feature Film', 'TV Series'
        job_class       [string]    job class ie 'camera department', 'cinematographer'
        job_title       [string]    specific job title
        first_year      [string]    first year credited
        last_year       [string]    last year credited
        genre_list      [str list]  list of genres for the overall title
                                    (only has content if no episodes listed)

        episode_list    list of episode objects representing episodes in screen credit
        season_list     list of season objects representing the seasons the episodes appeared in
        """
    def __init__(self, div, driver, session):
        self.div = div
        self.driver = driver
        self.title = div.find('a').text
        self._get_job_class_imdb_title_id()
        self.job_title = ''
        self.show_type = ''
        self._get_show_type_job_title()
        print(self.title + " (" + self.show_type + ")")
        self._get_years()
        self.episode_list = []
        self.season_list = []
        self._create_episode_list()
        self.genre_list = []
        if self.episode_list:
            self._create_season_list(session)
        if not self.season_list:
            show_page = ShowPage(driver, self.imdb_title_id)
            self.genre_list = show_page.genre_list

    def _get_job_class_imdb_title_id(self):
        job_class, self.imdb_title_id = self.div.attrs['id'].split('-')
        self.job_class = job_class.replace("_", " ")

    def _get_show_type_job_title(self):
        show_type_job_title = self.div.b.next_sibling.strip()
        # If that text chunk exists
        if show_type_job_title:
            # if that chunk consists of multiple parts, each in parentheses
            if ") (" in show_type_job_title:
                # split it into its individual elements
                elements = show_type_job_title.split(') (')
                # iterate through the list of elements
                for element in elements:
                    # if the element is a show type, then set show type to the element's value
                    if bool(re.search('TV|Docu|Short|Video', element)):
                        self.show_type = element.translate(element.maketrans('', '', '()'))
                    # if the element is a job description, set job desc to the element's value
                    elif bool(re.search(
                            'camera|AC|operator|photo|cinematograph|clapper'
                            '|imag|loader|puller|data|utility|dit|jib|tech|media'
                            '|pov|assistant|steadicam|video|light|electric|gaffer|grip',
                            element.lower())):
                        self.job_title = element.translate(element.maketrans('', '', '()'))
                # if job description is split into two different jobs
                if ' - ' in self.job_title:
                    # split it in two and assign job description to the first value
                    job_list = self.job_title.split(' - ')
                    self.job_title = job_list[0]
                # if the second chunk was not a show type, it was a status
                # (ie, 'completed', so the type is feature film
                if self.show_type == '':
                    self.show_type = 'Feature Film'
            # if that chunk consists of just one part
            else:
                # if it represents a show type, set show type to its value
                if bool(re.search('TV|Docu|Short|Video', show_type_job_title)):
                    self.show_type = show_type_job_title.translate(
                        show_type_job_title.maketrans('', '', '()'))
                # if it doesn't represent a show type, then it must be a job description.
                # Set job description to its value and show type to feature film
                # (which is never listed explicitly in imdb.
                else:
                    self.job_title = show_type_job_title.translate(
                        show_type_job_title.maketrans('', '', '()'))
                    self.show_type = 'Feature Film'
        # if the show type/job description text chunk doesn't exist
        else:
            # set show type to feature film, since it's never listed explicitly in imdb.
            self.show_type = 'Feature Film'
        # if the credit is listed in the Cinematographer section, then set job description to DP
        if self.job_class == 'cinematographer':
            self.job_title = 'director of photography'

    def _get_years(self):
        year = self.div.find('span', {'class': 'year_column'}).text.strip()
        # strip out roman numerals from the year column
        year = year.translate(year.maketrans('', '', '/I'))
        # if there's a range of years, separate it into first and last year
        if len(year) == 9:
            self.first_year = year[0:4]
            self.last_year = year[5:9]
        # if there's only one year, set first and last year equal to the same year
        else:
            self.first_year = year
            self.last_year = year

    def _create_episode_list(self):
        episode_divs = self.div.findAll('div', {'class': 'filmo-episodes'})
        if episode_divs:
            print(f"episode divs found for {self.title}")
            #for each episode div
            for episode_div in episode_divs:
                #find all the <a> elements in the episode div
                for link in episode_div.findAll('a'):
                    #if there's a link to an episode page
                    if 'href' in link.attrs:
                        job_title = ''
                        #Grab the episode job title credit from the episode credit (if it exists)
                        episode_title_job = episode_div.text.strip("\n)- ").split("\n... (")
                        if len(episode_title_job) == 2:
                            if bool(re.search('camera|AC|operator|photo|cinematograph|clapper'
                            '|imag|loader|puller|data|utility|dit|jib|tech|media'
                            '|pov|assistant|steadicam|video|light|electric|gaffer|grip',
                            episode_title_job[1].lower())):
                                job_title = episode_title_job[1]
                        imdb_episode_id = re.search('tt[0-9]{7,10}', link.attrs['href']).group(0)
                        print(f"episode_id: {imdb_episode_id}")

                        #Create an Episode object with the imdbTitleID of the episode and the
                        # job title credit
                        self.episode_list.append(Episode(imdb_title_id=self.imdb_title_id,
                                                         imdb_episode_id=imdb_episode_id,
                                                         job_title=job_title))

    def _create_season_list(self, session):
        # print(f"creating season list for {self.title}")
        for episode in self.episode_list:
            # print(f"checking neo4j for episode {episode.imdb_episode_id}")
            results = session.read_transaction(check_neo4j_for_episode, episode)
            if results.peek() is not None:
                print(f"episode {episode.imdb_episode_id} found in neo4j")
                for record in results:
                    if record['e.seasonNum'] is not None:
                        episode.season_num = int(record['e.seasonNum'])
                    if record['e.episodeNum'] is not None:
                        episode.episode_num = int(record['e.episodeNum'])
                    if record['e.airDate'] is not None:
                        episode.airdate = record['e.airDate'].to_native()
                genre_results = session.read_transaction(check_neo4j_for_episode_genre, episode)
                if genre_results.peek() is not None:
                    for record in genre_results:
                        episode.add_genre(record['g.genreName'])
            else:
                episode_page = EpisodePage(self.driver, episode)
                episode = episode_page.episode

                # If the episode has an airdate, season and episode numbers
                # (otherwise it's useless) add it to neo4j
                # print(f"episode {episode.imdb_episode_id}: airdate {episode.airdate},"
                #       f"season_num {episode.season_num}, episode_num {episode.episode_num}")
                if episode.airdate and episode.season_num and episode.episode_num:
                    print('     adding episode to neo4j: ', episode.episode_title,
                          episode.imdb_episode_id)
                    session.write_transaction(add_episode, episode)
                    session.write_transaction(add_genre_to_episode, episode)

        season_nums = {episode.season_num for episode in self.episode_list}

        if season_nums:
            for season_num in season_nums:
                if season_num:
                    self.season_list.append(Season(self.episode_list[0].imdb_title_id, season_num,
                                                   self.title))
            for season in self.season_list:
                for episode in self.episode_list:
                    if season.season_num == episode.season_num:
                        season.add_episode(episode)
                if season.job_title_list:
                    season.job_title_list = parse_job_list(season.job_title_list)
                else:
                    if self.job_class == 'cinematographer':
                        season.job_title_list = ['director of photography']


class Show(object):
    def __init__(self, imdb_title_id = None, show_title = None, genres = None):
        """imdbTitleID:     [string]    imdbTitleID of the show
           showTitle:       [string]    title of the show
           genres:          [string]    list of genres for the show in string form"""
        self.imdb_title_id = imdb_title_id
        self.show_title = show_title

        if genres:
            # convert the string "genres" into a python list of genres
            genres = genres.strip("[]")
            self.genre_list = genres.split(", ")
            for i in range(len(self.genre_list)):
                self.genre_list[i] = self.genre_list[i].strip("'")
        # if no genres exist, set the genre list to the null list
        else:
            self.genre_list = []


class ShowPage(Page):
    def __init__(self, driver, imdb_title_id):
        Page.__init__(self, driver, imdb_title_id)
        self.url = IMDB_TITLE_BASE_URL + self.imdb_id + '/'
        self._get_page(self.url)
        self.genre_list = []
        self._get_genres()

    def _get_genres(self):
        data = get_json(self.soup)
        if data:
            if 'genre' in data:
                self.genre_list = data['genre']


class Episode(object):
    def __init__(self, imdb_title_id=None, imdb_episode_id=None,
                 job_title=None, season_num=None, episode_num=None,
                 airdate=None, genre_list=None, episode_title=None):
        """imdbTitleID: [string]            imdbTitleID of the show
           imdbEpisodeID: [string]            imdb title code for the episode
           jobTitle:    [string]            job title from the episode credit
           seasonNum:   [int]               season number
           epNum:       [int]               episode number
           airDate:     [datetime.date]     first airdate of the episode
           genreList:   [list of strings]   genres of episode"""
        self.imdb_title_id = imdb_title_id
        self.imdb_episode_id = imdb_episode_id
        self.job_title = job_title
        self.season_num = season_num
        self.episode_num = episode_num
        self.airdate = airdate
        self.genre_list = genre_list
        self.episode_title = episode_title

    @property
    def imdb_season_id(self):
        if self.season_num:
            return self.imdb_title_id + "S" + str(self.season_num)
        else:
            return None

    @property
    def airdate_string(self):
        """Returns a string representation of the airDate if one exists,
        returns empty string if not"""
        if self.airdate:
            return self.airdate.strftime('%Y-%m-%d')
        else:
            return None

    @property
    def genre_list(self):
        if self._genre_list:
            self._genre_list.sort()
        return self._genre_list

    @genre_list.setter
    def genre_list(self, genre_list):
        self._genre_list = genre_list

    @property
    def genre_string(self):
        """Returns a string representation of the genre list"""
        return ", ".join(self.genre_list)

    def add_genre(self, genre):
        """genre:   [string]"""
        if not self._genre_list:
            self._genre_list = []
        self._genre_list.append(genre)

    def __lt__(self, other):
        return self.episode_num < other.episode_num

    def __str__(self):
        return self.imdb_episode_id + ", " + str(self.season_num) + ", " \
               + str(self.episode_num) + ", " \
               + self.airdate_string + ", " + self.genre_string


class Season(object):
    def __init__(self, imdb_title_id, season_num, show_title=None):
        """imdbTitleID:     [string]        imdbTitleID of the show the season is part of
           seasonNum:       [int]           season number"""
        self.imdb_title_id = imdb_title_id
        self.season_num = season_num
        self.episode_list = []
        self.airdate_list = []
        self.job_title_list = []
        self.genre_list = []
        self.show_title = ""
        if show_title:
            self.show_title = show_title

    def add_episode(self, episode):
        """Adds an Episode object to the season's episode list and its airDate
        to the season's airDateList"""
        self.episode_list.append(episode)
        if episode.airdate:
            self.airdate_list.append(episode.airdate)
        if episode.genre_list:
            for genre in episode.genre_list:
                if genre not in self.genre_list:
                    self.genre_list.append(genre)
        if episode.job_title:
            if episode.job_title not in self.job_title_list:
                self.job_title_list.append(episode.job_title)

    def add_air_date(self, airDate):
        """Adds an airDate (datetime.date object) to the airDateList"""
        self.airdate_list.append(airDate)

    @property
    def first_airdate(self):
        """Returns a string representation of the earliest date and None if no dates"""
        if self.airdate_list:
            return min(self.airdate_list).strftime('%Y-%m-%d')
        else:
            return None

    @property
    def last_airdate(self):
        """Returns a string representation of the latest date and None if no dates"""
        if self.airdate_list:
            return max(self.airdate_list).strftime('%Y-%m-%d')
        else:
            return None

    @property
    def imdb_season_id(self):
        """Generates an imdbSeasonID for the season based on imdbTitleID and season number"""
        return self.imdb_title_id + "S" + str(self.season_num)

    @property
    def rough_start(self):
        """Returns string representation of the first day of the year of the first airdate"""
        if self.first_airdate:
            return self.first_airdate[:-5] + "01-01"
        else:
            return None

    @property
    def rough_end(self):
        """Returns string representation of the last day of the year of the last airdate"""
        if self.last_airdate():
            return self.last_airdate()[:-5] + "12-31"
        else:
            return None

    @property
    def season_title(self):
        return self.show_title + " S" + str(self.season_num)


class EpisodePage(Page):
    def __init__(self, driver, episode):
        Page.__init__(self, driver, episode.imdb_episode_id)
        self.url = IMDB_TITLE_BASE_URL + self.imdb_id + '/'
        self.episode = episode
        self._get_page(self.url)
        json_data = get_json(self.soup)
        self.episode.episode_title = h.unescape(json_data['name'])
        self.episode.genre_list = json_data['genre']

        self._get_season_episode_nums()
        self._get_airdate()

    def _get_season_episode_nums(self):
        season_num = None
        episode_num = None
        se = self.soup.select_one('ul[data-testid="hero-subnav-bar-season-episode-numbers-section"]')
        if se:
            for child in se.find_all('li'):
                child = child.text.strip()
                if child.startswith('S'):
                    season_num = int(child[1:])
                if child.startswith('E'):
                    episode_num = int(child[1:])
        self.episode.season_num = season_num
        self.episode.episode_num = episode_num

    def _get_airdate(self):
        # Search for <li> with episode air date
        # Extract air date if it exists and convert to datetime object
        airdate_string = ''
        airdate_lis = self.soup('li', text=re.compile(r'Episode air'))
        if airdate_lis:
            airdate_string = airdate_lis[0].text.strip()
            if 'Episode aired' in airdate_string:
                airdate_string = airdate_string[14:]
            elif 'Episode airs' in airdate_string:
                airdate_string = airdate_string[13:]

        self.episode.airdate = date_string_to_date(airdate_string)


class EpisodeListPage(Page):
    def __init__(self, driver, show):
        Page.__init__(self, driver, show.imdb_title_id)
        self.url = IMDB_TITLE_BASE_URL + self.imdb_id + '/episodes'
        self.show = show
        self.episode_list = []
        self.season_list = []
        self.option_list = []
        self.selected = None
        self.page_layout = ''
        self._get_page(self.url)

    def _get_options_div(self, for_label):
        label = self.soup.find('label', {'for': {for_label}})
        if label is not None:
            options_div = label.parent
            options = options_div.find_all('option', {'value': {re.compile('[0-9]{1,4}')}})
            for option in options:
                if int(option['value'].strip()) > 0:
                    self.option_list.append(option.text.strip())
                    if option.has_attr('selected'):
                        if option['selected'] == 'selected':
                            self.selected = int(option['value'].strip())
        if for_label == 'bySeason':
            self.page_layout = 'season'
        elif for_label == 'byYear':
            self.page_layout = 'year'

    def get_all_episodes_by_year_or_season(self):
        self._get_options_div('bySeason')
        if not self.option_list:
            self._get_options_div('byYear')
        for option in self.option_list:
            if self.selected:
                if int(option) > self.selected:
                    break
            url = IMDB_TITLE_BASE_URL + self.imdb_id + '/episodes?' + \
                  self.page_layout + '=' + option
            self._get_page(url)
            self._get_episodes_for_one_year_or_season()

    def _get_episodes_for_one_year_or_season(self):
            episode_divs = self.soup.find_all('div', {'class': {re.compile('list_item [a-z]{1,4}')}})
            for episode_div in episode_divs:
                episode_title = ''
                imdb_episode_id = ''
                season_num = ''
                episode_num = ''
                airdate = None

                # Find Episode Title
                title_a = episode_div.find('a', {'itemprop': {'name'}})
                if title_a:
                    episode_title = title_a.text.strip()

                # Find IMDB Episode ID, Season Number, Episode Number
                data_div = episode_div.find('div', {'data-const': True})
                if data_div:
                    imdb_episode_id = data_div['data-const']
                    season_ep_numbers_div = data_div.find('div')
                    if season_ep_numbers_div:
                        season_ep_numbers_text = season_ep_numbers_div.text.strip()
                        if season_ep_numbers_text:
                            if season_ep_numbers_text == 'Unknown':
                                continue
                            season_text, ep_text = season_ep_numbers_text.split(', ')
                            try:
                                season_num = re.search('[0-9]{1,4}', season_text).group(0)
                            except AttributeError:
                                season_num = ''
                            try:
                                episode_num = re.search('[0-9]{1,4}', ep_text).group(0)
                            except AttributeError:
                                episode_num = ''

                # Find airdate
                airdate_div = episode_div.find('div', {'class': {'airdate'}})
                if airdate_div:
                    airdate_text = airdate_div.text.strip().replace(".", "")
                    airdate = date_string_to_date(airdate_text)

                self.episode_list.append(Episode(imdb_title_id=self.imdb_id,
                                                 imdb_episode_id=imdb_episode_id,
                                                 season_num=int(season_num),
                                                 episode_num=episode_num,
                                                 airdate=airdate,
                                                 episode_title=episode_title))

                # print("Episode Title: ", episode_title)
                # print("IMDB Episode ID: ", imdb_episode_id)
                # print("Season Number: ", season_num)
                # print("Episode Number: ", episode_num)
                # print("Airdate: ", airdate.strftime('%Y-%m-%d'))
                # print("\n")

    """
    Populates the season list with seasons whose episodes fell within a particular year
    """
    def get_seasons_for_year(self, year):
        self._get_options_div('byYear')
        if year in self.option_list:
            url = IMDB_TITLE_BASE_URL + self.imdb_id + '/episodes?year=' + year
            self._get_page(url)
            self._get_episodes_for_one_year_or_season()
            self.get_seasons_from_episodes()

    def get_seasons_from_episodes(self):
        if self.episode_list:
            season_nums = {episode.season_num for episode in self.episode_list}
            if season_nums:
                for season_num in season_nums:
                    if season_num:
                        self.season_list.append(Season(self.episode_list[0].imdb_title_id,
                                                       season_num, self.show.show_title))
                for season in self.season_list:
                    for episode in self.episode_list:
                        if season.season_num == episode.season_num:
                            season.add_episode(episode)


def date_string_to_date(date_string):
    if re.match('[0-9]{1,2} [A-Za-z]{4,9} [0-9]{4}', date_string):
        return datetime.strptime(date_string, '%d %B %Y').date()
    elif re.match('[A-Za-z]{3} [0-9]{1,2}, [0-9]{4}', date_string):
        return datetime.strptime(date_string, '%b %d, %Y')
    elif re.match('[0-9]{1,2} [A-Za-z]{3} [0-9]{4}', date_string):
        return datetime.strptime(date_string, '%d %b %Y').date()
    elif re.match('[A-Za-z]{4,9} [0-9]{4}', date_string):
        return datetime.strptime(date_string, '%B %Y').date()
    elif re.match('[A-Za-z]{3} [0-9]{4}', date_string):
        return datetime.strptime(date_string, '%b %Y').date()
    elif re.match('[0-9]{4}', date_string):
        return datetime.strptime(date_string, '%Y').date()
    else:
        return None


def add_genre(tx, genre_name):
    tx.run("MERGE (g:Genre {genreName: $genreName}) "
           "ON CREATE SET g.uuid = apoc.create.uuid() ",
           genreName=genre_name)


def add_person(tx, person):
    full_name = person.full_name
    imdb_name_id = person.imdb_name_id
    tx.run("MERGE (a:Person {imdbNameID: $imdbNameID})"
           "ON CREATE SET a.createdDate = datetime(), "
           "a.uuid = apoc.create.uuid(), a.fullName = $fullName ",
           fullName=full_name, imdbNameID=imdb_name_id,)


def get_crew_list(tx, label):
    return tx.run("MATCH (p) WHERE $label IN labels(p) "
                  "RETURN p.imdbNameID, p.fullName ",
                  label=label)


def check_neo4j_for_episode(tx, episode):
    imdb_episode_id = episode.imdb_episode_id
    return tx.run("MATCH(e:Episode {imdbEpisodeID: $imdbEpisodeID})"
                  "RETURN e.seasonNum, e.episodeNum, e.airDate",
                  imdbEpisodeID=imdb_episode_id)


def check_neo4j_for_episode_genre(tx, episode):
    imdb_episode_id = episode.imdb_episode_id
    return tx.run("MATCH(e:Episode {imdbEpisodeID: $imdbEpisodeID})-[:HAS_GENRE]->(g:Genre)"
                  "RETURN g.genreName",
                  imdbEpisodeID=imdb_episode_id)


def add_episode(tx, episode):
    imdb_episode_id = episode.imdb_episode_id
    imdb_season_id = episode.imdb_season_id
    imdb_title_id = episode.imdb_title_id
    season_num = episode.season_num
    episode_num = episode.episode_num
    airdate = episode.airdate_string
    episode_title = episode.episode_title

    tx.run("MERGE(e:Episode {imdbEpisodeID: $imdbEpisodeID}) "
           "ON CREATE SET e.createdDate = datetime(), e.imdbSeasonID = $imdbSeasonID, "
           "e.imdbTitleID = $imdbTitleID, "
           "e.seasonNum = $seasonNum, e.episodeNum = $episodeNum, e.airDate = date($airDate), "
           "e.episodeTitle = $episodeTitle, e.uuid = apoc.create.uuid() "
           "WITH e "
           "MATCH(se:Season {imdbSeasonID: $imdbSeasonID}) "
           "MERGE(e)-[:EPISODE_OF]->(se)",
           imdbEpisodeID=imdb_episode_id, imdbSeasonID=imdb_season_id, imdbTitleID=imdb_title_id,
           seasonNum=season_num, episodeNum=episode_num, airDate=airdate,
           episodeTitle=episode_title)


def add_genre_to_episode(tx, episode):
    imdb_episode_id = episode.imdb_episode_id
    genre_list = episode.genre_list
    if genre_list:
        for genre in genre_list:
            tx.run("MATCH(e:Episode {imdbEpisodeID: $imdbEpisodeID})"
                   "MATCH(g:Genre {genreName:$genre})"
                   "MERGE(e)-[:HAS_GENRE]->(g)", imdbEpisodeID=imdb_episode_id, genre=genre)


def parse_job_list(job_list):
    """
    Parses and standardizes a raw list of camera/g&e department job titles from IMDb
    """
    job_titles = ['first assistant camera', 'second assistant camera', 'lead assistant camera',
                  'assistant camera', 'camera operator', 'director of photography',
                  'camera utility', 'steadicam operator', 'additional camera operator',
                  'best boy electric', 'key grip', 'lighting director']
    split_jobs = []
    for job in job_list[:]:
        if ") / (" in job:
            jobs = job.split(") / (")
            for j in jobs:
                split_jobs.append(j)
            job_list.remove(job)

    for job in job_list[:]:
        if " / " in job:
            jobs = job.split(" / ")
            for j in jobs:
                split_jobs.append(j)
            job_list.remove(job)

    for job in split_jobs:
        if job not in job_list:
            job_list.append(job)

    base_jobs = []
    for job in job_list[:]:
        if " - " in job:
            base_job = job.split(" - ")[0]
            base_jobs.append(base_job)
            job_list.remove(job)
    for job in base_jobs:
        if job not in job_list:
            job_list.append(job)

    base_jobs = []
    for job in job_list[:]:
        if ": " in job:
            base_job = job.split(": ")[0]
            base_jobs.append(base_job)
            job_list.remove(job)
    for job in base_jobs:
        if job not in job_list:
            job_list.append(job)

    reordered = []
    for i in job_list[:]:
        for j in job_titles:
            lower_i = i.lower()
            lower_j = j.lower()
            if set(lower_i.split()) == (set(lower_j.split())):
                if j not in reordered:
                    reordered.append(j)
                job_list.remove(i)
    job_list.extend(reordered)

    for job in job_list[:]:
        if re.match('\"[a-fA-F]{1}\" ', job):
            print("\'match\'")
            temp = job[4:]
            job_list.remove(job)
            if temp not in job_list:
                job_list.append(temp)
        if re.match('[a-fA-F]{1} ', job):
            print("match")
            temp = job[2:]
            job_list.remove(job)
            if temp not in job_list:
                job_list.append(temp)
        if re.match('Additional |additional ', job):
            temp = job[11:]
            job_list.remove(job)
            if temp not in job_list:
                job_list.append(temp)
        if re.match('as |As ', job):
            job_list.remove(job)
    return job_list


def to_caps(str):
    conj = ['the', 'of', 'or', 'a']
    results = []
    str = str.lower()
    word_list = str.split()
    for word in word_list:
        if word not in conj:
            word = word.title()
        results.append(word)
    result = ' '.join(results)
    return result


def open_imdb_browser():
    # Set Chrome preferences
    chrome_options = webdriver.ChromeOptions()
    prefs = {
        'profile.default_content_settings':
        {
            'cookies': 2,
            # 'images': 2,
            # 'javascript': 2
        },
        # 'profile.managed_default_content_settings':
        # {
        #     'images': 2,
        #     'javascript': 2
        # }
             }
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.add_argument('--enable-automation')

    # Instantiate webdriver and navigate to IMDB login page
    driver = webdriver.Chrome(options=chrome_options)

    j = 5
    while j > 0:
        try:
            driver.get(config.imdb_signin_url)
            break
        except TimeoutException:
            driver.refresh()
            j -= 1

    # Log in to IMDBPro account
    email = config.imdb_username
    password = config.imdb_password

    un = driver.find_element_by_id('ap_email')
    un.send_keys(email)

    ps = driver.find_element_by_id('ap_password')
    ps.send_keys(password)

    li = driver.find_element_by_id('signInSubmit')
    li.click()

    pause = input("Hit enter after captcha: ")

    return driver


def open_neo4j_session():
    neo_driver = GraphDatabase.driver \
        (config.neo4j_host,
         auth=basic_auth(config.neo4j_user, config.neo4j_password))
    return neo_driver
