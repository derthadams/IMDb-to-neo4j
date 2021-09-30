import csv
import imdb_to_neo4j as i2n
import config


def get_seasons_and_year_set(session, show, first_year, last_year):
    results = session.read_transaction(i2n.check_neo4j_for_season_years,
                                       show, first_year, last_year)
    if results is None:
        return [], set()
    else:
        season_ids = []
        season_years = set()
        for result in results:
            imdb_season_id = result['imdbSeasonID']
            rough_start = result['roughStart']
            rough_end = result['roughEnd']
            season_years.add(range(int(rough_start[:4]),
                                   int(rough_end[:4]) + 1))
            season_ids.append(imdb_season_id)
        return season_ids, season_years


def process_imdb_title_id(driver, session, show):
    episode_page = i2n.EpisodeListPage(driver, show)
    episode_page.get_all_episodes_by_year_or_season()
    episode_page.get_seasons_from_episodes()
    session.write_transaction(i2n.add_show, show, 'imdb_p')
    for season in episode_page.season_list:
        print("Adding season", season.season_title, "from new process")
        session.write_transaction(i2n.add_season, season, 'imdb_p')
        session.write_transaction(i2n.add_season_of, season, show)
    return episode_page.season_list


def main():
    # Instantiate neo4j driver
    neo_driver = i2n.open_neo4j_session()

    # Instantiate webdriver and navigate to IMDB login page
    driver = i2n.open_imdb_browser()

    while True:
        try:
            person_season_csv = input("File path of the Person-Season List: ")
            skip = int(input("Number of rows to skip: "))

            # Load person-season data from the CSV file
            with neo_driver.session() as session:
                with open(person_season_csv) as f:
                    reader = csv.reader(f)
                    for _ in range(skip):
                        next(reader)
                    for (full_name, imdb_name_id, job_class, job_title, first_year, last_year,
                         show_title, imdb_title_id, season_num, show_type, genres) in reader:

                        if imdb_title_id in config.blacklist:
                            continue

                        show = i2n.Show(imdb_title_id, show_title, genres)
                        crew = i2n.Person(imdb_name_id, full_name)
                        season = None

                        if season_num:
                            season = i2n.Season(imdb_title_id, season_num, show_title)

                        print(f"Now processing {imdb_title_id} {show_title} {full_name}")

                        # No season information
                        if not season:

                            # No years worked information
                            if not first_year and not last_year:

                                # Check to see if show is in neo4j
                                results = session.read_transaction(i2n.check_neo4j_for_show, show)

                                # If show isn't in neo4j
                                if results.peek() is None:
                                    # Scrape IMDb for the show and all its seasons and add to neo4j
                                    process_imdb_title_id(driver, session, show)

                                # Add WORKED_ON relationship between crew and show
                                session.write_transaction(i2n.add_worked_on_show,
                                                          crew.imdb_name_id,
                                                          job_title, show.imdb_title_id,
                                                          'imdb_i')
                                continue

                            # Has years worked information
                            else:
                                # Search neo4j for seasons corresponding to years
                                worked_years = set(range(int(first_year), int(last_year) + 1))
                                season_ids, season_years = get_seasons_and_year_set(session, show,
                                                                                    first_year,
                                                                                    last_year)
                                # If no results or incomplete results
                                if not season_ids or not worked_years.issubset(season_years):
                                    # Scrape IMDb for show and all seasons, add to neo4j
                                    process_imdb_title_id(driver, session, show)
                                    season_ids, season_years = get_seasons_and_year_set(session,
                                                                                        show,
                                                                                        first_year,
                                                                                        last_year)
                                # Add WORKED_ON relationships between crew and all seasons found
                                for imdb_season_id in season_ids:
                                    session.write_transaction(i2n.add_worked_on_season,
                                                                  crew.imdb_name_id, job_title,
                                                                  imdb_season_id, 'imdb_i')
                                # Add WORKED_ON relationship between crew and show
                                session.write_transaction(i2n.add_worked_on_show, crew.imdb_name_id,
                                                          job_title, show.imdb_title_id, 'imdb_i')
                        # Season information
                        else:
                            # Check neo4j for season
                            results = session.read_transaction(i2n.check_neo4j_for_season, season)

                            # Season is in neo4j
                            if results.peek() is not None:
                                # Add WORKED_ON relationship between crew and season
                                session.write_transaction(i2n.add_worked_on_season, imdb_name_id,
                                                          job_title, season.imdb_season_id,
                                                          'imdb_p')
                            # Season not in neo4j
                            else:
                                # Scrape IMDb for show and all seasons, add to neo4j
                                process_imdb_title_id(driver, session, show)
                                # Add WORKED_ON relationship between crew and season
                                session.write_transaction(i2n.add_worked_on_season, imdb_name_id,
                                                          job_title, season.imdb_season_id,
                                                          'imdb_p')

                            # Add WORKED_ON relationship between crew and show
                            session.write_transaction(i2n.add_worked_on_show, crew.imdb_name_id,
                                                      job_title, show.imdb_title_id, 'imdb_p')

            session.close()
            break

        except FileNotFoundError:
            print("File not found")
    driver.quit()


main()
