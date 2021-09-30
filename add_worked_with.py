import imdb_to_neo4j as i2n


def update_worked_with(tx, person):
    imdb_name_id = person.get_imdb_name_id()
    return tx.run("MATCH(p1:Person {imdbNameID: $imdb_name_id}) "
                  "MATCH(p1)-[:WORKED_ON]->(se:Season)<-[:WORKED_ON]-(p2) "
                  "WHERE p1 <> p2 AND NOT (p1)-[:WORKED_WITH]-(p2) "
                  "WITH p1, p2, se "
                  "ORDER BY se.roughStart DESC "
                  "WITH p1, p2, min(se.roughStart) AS startDate, "
                  "     max(se.roughEnd) AS endDate, "
                  "     count(distinct se) AS seasons_in_common, "
                  "     collect(distinct se.seasonTitle + ' (' + "
                  "    toString(se.roughStart.year) + ')')[..5] AS season_list "
                  "WHERE startDate IS NOT null AND endDate IS NOT null  "
                  "MERGE(p1)-[r:WORKED_WITH]->(p2) "
                  "ON CREATE SET r.createdDate = datetime(), "
                  "     r.startDate = startDate, r.endDate = endDate, "
                  "     r.seasons_in_common = seasons_in_common, "
                  "     r.season_list = season_list, "
                  "     r.uuid = apoc.create.uuid() "
                  "RETURN p1.fullName AS name1, p2.fullName AS name2, "
                  "     startDate AS startDate, endDate AS endDate, "
                  "     seasons_in_common AS seasons_in_common, season_list ",
                  imdb_name_id=imdb_name_id)


def main():
    neo_driver = i2n.open_neo4j_session()
    crew_list = []
    with neo_driver.session() as session:
        results = session.read_transaction(i2n.get_crew_list, 'Person')
        for result in results:
            if result['p.imdbNameID']:
                crew_list.append(i2n.Person(result['p.imdbNameID'],
                                               result['p.fullName']))
        for crew in crew_list:
            print("Now processing: ", crew.full_name)
            results = session.write_transaction(update_worked_with, crew)
            if results.peek():
                for result in results:
                    print("Updated: ", result['name1'], " - ", result['name2'],
                          " - ", result['startDate'], " - ", result['endDate'],
                          " - ", result['seasons_in_common'])
            else:
                print("Crew: ", crew.full_name, " does not have an update list")
    session.close()


main()



