import imdb_to_neo4j as i2n
import csv
import re


def main():
    driver = i2n.open_imdb_browser()
    neo_driver = i2n.open_neo4j_session()

    # Get the filename for the CSV list of crew people to process
    while True:
        try:
            crew_csv = input("File path of the Crew List: ")
            skip = int(input("Number of rows to skip: "))
            # Load URLs from the CSV file
            with open(crew_csv) as f:
                reader = csv.reader(f)
                for i in range(skip):
                    next(reader)
                crew_list = []
                for imdb_name_id, full_name in reader:
                    crew_list.append(i2n.Person(imdb_name_id, full_name))
            break
        except FileNotFoundError:
            print("File not found")

    with open(crew_csv[:-4] + '_results.csv', mode='w') as results_file:
        fieldnames = ['name', 'name_id', 'job_class', 'job_title',
                      'first_year', 'last_year', 'show_title', 'title_id',
                      'season', 'show_type', 'show_genres', ]
        csvwriter = csv.writer(results_file)
        csvwriter.writerow(fieldnames)

        with neo_driver.session() as session:
            for crew in crew_list:
                print("\nNow processing", crew.full_name)
                name_page = i2n.NamePage(driver, session, crew)
                for credit in name_page:
                    if re.match("TV", credit.show_type) and re.search("Series", credit.show_type):
                        if credit.season_list:
                            for season in credit.season_list:
                                if ((credit.first_year and credit.last_year) or
                                   season.first_airdate and season.last_airdate):
                                    for job in season.job_title_list:
                                        row = [
                                            crew.full_name,
                                            crew.imdb_name_id,
                                            i2n.to_caps(credit.job_class),
                                            i2n.to_caps(job),
                                            credit.first_year,
                                            credit.last_year,
                                            credit.title,
                                            credit.imdb_title_id,
                                            str(season.season_num),
                                            credit.show_type,
                                            season.genre_list,
                                        ]
                                        csvwriter.writerow(row)
                                else:
                                    row = [
                                        crew.full_name,
                                        crew.imdb_name_id,
                                        i2n.to_caps(credit.job_class),
                                        i2n.to_caps(credit.job_title),
                                        credit.first_year,
                                        credit.last_year,
                                        credit.title,
                                        credit.imdb_title_id,
                                        None,
                                        credit.show_type,
                                        credit.genre_list,
                                    ]
                                    csvwriter.writerow(row)
        session.close()
    driver.quit()


main()
