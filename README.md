# IMDb-to-neo4j

- [Introduction](#introduction)
- [Installation](#installation)
- [Using IMDb-to-neo4j](#using)

<a name="introduction"></a>
## Introduction
I started this project because I wanted to study the collaboration networks of camera professionals 
working in the TV industry, and I needed a way to gather and analyze data.

TV freelancers work on short-term assignments for many different employers, and find work through 
informal peer networks. 
I wanted to be able to visualize these networks and use graph algorithms to analyze them.

I decided to use the property graph database neo4j as a data store, since it allows for efficient 
queries of highly connected data. To source the data I chose to scrape IMDb, an online crowdsourced 
database of film and TV credits which includes information on pretty much everyone who works in the 
industry.

There were a few challenges to using IMDb as a data source:

- Since IMDb has no public API, I needed to discover patterns in the structure of the page source 
that would allow me to find the data I wanted. This is a bit of a moving target since IMDb is 
continuously being redeveloped. I've already had to rework my code a few times to account for 
changes in the way the site is structured.

- IMDb is crowdsourced, so the completeness and quality of the data can be spotty. I couldn't count 
on all fields being available for all records, so in my scraping code I had to account for cases 
where any given field was missing.
	
- In order to reliably detect a collaboration between two crew members, I needed to know whether 
they had both worked on a particular season of a show. IMDb's schema does not include seasons of 
shows as entities: it only has shows and episodes as entities, and seasons exist as metadata on the 
episodes. Since shows are too general for detecting collaborations and episodes are too specific, 
I had to generate season entities by combining data from the related show and episode entities.

- Because IMDb displays credits in a truncated format by default, I had to scrape the pages as a 
logged-in user in order to select an expanded format in the user preferences that would display all 
the data on the page at once. In order to handle user authentication I had to scrape the site by 
controlling a Chrome browser with Selenium instead of using a more lightweight library like 
requests.

### Schemas

The following two diagrams show the approximate relational schema for the IMDb source data, and the 
graph schema for my neo4j datastore. Since seasons don't exist as entities in IMDb, my code 
generates them from the related show and episode entities.

![IMDb schema](https://user-images.githubusercontent.com/39425112/135365993-7b0729cc-a1c8-4b21-9cc3-90ca4f127f78.png)

| IMDb Relational Schema |
| :----: |

![neo4j schema](https://user-images.githubusercontent.com/39425112/135366038-76c46fa4-366d-4775-a07e-e54d3b4f6cc5.png)

| neo4j Graph Schema |
| :----: |

Not only does the code scrape data and store it, it also cleans and transforms the data
into a different schema.

### Code organization
I structured my code in two parts:
1. A library `imdb-to-neo4j.py` which contains multipurpose classes and functions that handle scraping 
the IMDb pages and interacting with the neo4j database.
2. Standalone scripts that use `imdb-to-neo4j.py` to accomplish individual tasks:
    1. `add_people.py`: takes a list of people with their IMDb identifiers and adds them to the neo4j 
    database
    2. `scrape_name_list.py`: takes a list of people, scrapes their credits from IMDb, and outputs a 
    csv containing the credit information.
    3. `add_worked_on.py`: takes the credit csv output by scrape_name_list, adds WORKED_ON 
    relationships between people, seasons, and shows in the neo4j database, and also adds the 
    seasons and shows if they're not yet in the database.
    4. `add_worked_with.py`: searches for people who have both worked on the same season and adds a 
    WORKED_WITH relationship between them.

<a name="installation"></a>
## Installation

### Linux and macOS

IMDB-to-neo4j and its dependencies require Python 3.7, as well as 
[pip](https://pip.pypa.io/en/stable/) and 
[virtualenv](https://pypi.org/project/virtualenv/).

Navigate to the directory where you want to install IMDb-to-neo4j and create a virtual environment 
with Python 3.7

    python3 -m virtualenv --python=<path/to/python3.7> <environment-name>
    
Activate the virtual environment

    source <environment-name>/bin/activate

Initialize git

    git init
    
Clone the IMDb-to-neo4j git repository, either

- via https
    
        git clone https://github.com/derthadams/IMDb-to-neo4j.git
    
- or via ssh

        git clone git@github.com:derthadams/IMDb-to-neo4j.git
    
Navigate to the project directory

    cd IMDb-to-neo4j
    
and install the project dependencies using pip

    python3 -m pip install -r requirements.txt

<a name="using"></a>
## Using IMDb-to-neo4j

### Additional dependencies
Running this project requires that you have an installed and active 
[neo4j 3.5 Community Version](https://neo4j.com/download-center/#community) database instance, as 
well as [Google Chrome](https://www.google.com/chrome/) and 
[ChromeDriver](https://chromedriver.chromium.org).

### config file
Secrets for your IMDb account and neo4j database are stored in a file called `config.py` which you 
should create inside the main project directory `IMDb-to-neo4j`.

It should have the following format:

    imdb_username = <your_imdb_username>
    imdb_password = <your_imdb_password>

    neo4j_host = <your_neo4j_URL/port_number>
    neo4j_user = <your_neo4j_user>
    neo4j_password = <your_neo4j_password>
    
    blacklist = [<list of IMDb title identifiers>]
    
`blacklist` is an optional list of IMDb identifiers for titles that you want IMDb-to-neo4j to 
ignore during processing. 

### Preparing the neo4j database

The first thing you should do before running any other scripts is to add all IMDb genres 
to the neo4j database by running the file `add_genres.py`

    python3 add_genres.py
    
### Scraping credits

#### Adding people to neo4j
Prepare a csv file with the IMDb identifiers and full names of the people whose credits you want to 
scrape:

*people.csv*
    
| imdb_name_id | full_name |
| ------------ | --------- |
| nm0003113 | Derth Adams |
| ... | ... |

You can find the IMDb identifier for a person by searching for their profile page on IMDb. In the
URL for the page you'll find the identifier, which starts with 'nm' and has 7 or 8 digits 
immediately afterwards.

If any of the people in the csv file are not already in the neo4j database, run `add_people.py`

    python3 add_people.py
    
You will get a prompt for the csv file path.

    File path of the Person List: 
    
Enter the file path

    > people.csv
    
and you'll then get a prompt

    Number of rows to skip:
    
If you want to scrape credits for the entire list and you have a header row in your csv, enter 1, 
otherwise enter 0. If you want to skip a certain number of rows of people, enter the number of rows 
you want to skip. This can be useful if you're processing names in batches.
    
The script will then start adding people to neo4j and you'll see a confirmation for each person as 
they're added.

    Adding IMDb name ID: nm0003113, Full name: Derth Adams
    
#### Scraping credits for the list of people
Once you have all the people added, you can scrape their credits by running `scrape_name_list.py`

    python3 scrape_name_list.py
    
Next you'll get the prompt

    Number of rows to skip:
    
Chrome will launch and the script will log in to your IMDb account and take you to the IMDb home 
page. At this point, sometimes IMDb will give you a CAPTCHA to complete.

<a name="chrome"></a>
At this point it's a good idea to turn off Javascript and images, which will greatly speed up 
scraping. Go to Chrome -> Preferences -> Privacy and Security -> Site Settings and turn off the 
options for Javascript and Images.

At first I tried disabling Javascript and images automatically in the initial WebDriver settings,
but since any CAPTCHA you receive will require both of those to be turned on, it's unfortunately
necessary to turn them off manually.

In the console, you'll see

    Hit enter to continue:
    
Hit enter and you'll be prompted for the file path of the person list csv

    File path of the Person List: 
    
and then

    Number of rows to skip:

Once you've entered the number of rows, the script will begin visiting the profile page for each 
person on the list, and each episode of each show that they're listed as working on will be 
recursively scraped in order to generate season entities.

The script will check neo4j first for any episodes to try and avoid having to scrape the page, and 
will save any new episodes it encounters back to neo4j.

After scraping is completed Chrome will quit and you can find a csv results file in the same 
directory as your original list of names. The filename will be:

    <your_name_list>_results.csv
    
It will have the following format:

**people_results.csv**

| name | name_id | job_class | job_title | first_year | last_year | show_title | title_id | season | show_type | show_genres |
| ---- | ------- | --------- | --------- | ---------- | --------- | ---------- | -------- | ------ | --------- | ----------- |
| Derth Adams | nm0003113 | Camera Department | Camera Operator | 2021 | 2021 | Wipeout | tt13117230 | 1 | TV Series | ['Comedy', 'Game-Show'] |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Adding WORKED_ON relationships to neo4j

After you've run `scrape_name_list.py` and have a result csv of people's credits, you can add those 
credits to neo4j using `add_worked_on.py`

    python3 add_worked_on.py
    
Chrome will launch and you'll be logged in to your IMDb account and taken to the home page.
At this point you'll get the prompt

    Hit enter to continue:

which allows you time to complete any CAPTCHA that IMDb give you, as well as turn off Javascript 
and image loading (as covered in [this section above](#chrome)).
    
After you hit enter you'll get a prompt for the credit results csv

    File path of the Person-Season List: 
    
and then

    Number of rows to skip:
    
Once you've entered the number of rows, the script will begin adding WORKED_ON relationships to 
neo4j based on the credits in the csv.
If any shows or seasons in the credit results csv aren't currently in the neo4j database, the script
will use Chrome to scrape the corresponding pages to get the data.

### Adding WORKED_WITH relationships to neo4j

The final step in creating the collaboration graph is to create WORKED_WITH relationships between 
any two
people who have worked on the same TV show season. You can do this by using `add_worked_with.py`:

    python3 add_worked_with.py
    
The script will then run queries in neo4j that will find all people who have worked together on the
same TV show season, and create WORKED_WITH relationships between them. For each relationship
created you'll see a status update in the console.