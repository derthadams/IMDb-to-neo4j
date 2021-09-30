import imdb_to_neo4j as i2n
import csv


def main():
    neo_driver = i2n.open_neo4j_session()

    while True:
        try:
            person_csv = input("File path of the Person List: ")
            # Load person-season data from the CSV file
            with neo_driver.session() as session:
                with open(person_csv) as f:
                    reader = csv.reader(f)
                    next(reader)
                    for imdb_name_id, full_name in reader:
                        if imdb_name_id:
                            print(f"Adding IMDb name ID: {imdb_name_id}, Full name: {full_name}")
                            session.write_transaction(i2n.add_person,
                                                      i2n.Person(imdb_name_id, full_name))
            session.close()
            break
        except FileNotFoundError:
            print("File not found")


main()
