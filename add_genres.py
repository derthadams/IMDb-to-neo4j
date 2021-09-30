import imdb_to_neo4j as i2n


def main():
    neo_driver = i2n.open_neo4j_session()

    genre_names = [
        'Comedy',
        'Mystery',
        'Reality-TV',
        'Documentary',
        'Biography',
        'History',
        'Talk-Show',
        'Drama',
        'Music',
        'Game-Show',
        'Sport',
        'Crime',
        'Adventure',
        'Family',
        'Thriller',
        'Romance',
        'Action',
        'Western',
        'Sci-Fi',
        'Horror',
        'Musical',
        'War',
        'News',
        'Short',
        'Fantasy',
        'Animation',
        'Adult',
        'Film Noir'
    ]

    with neo_driver.session() as session:
        for genre_name in genre_names:
            session.write_transaction(i2n.add_genre, genre_name)
    session.close()


main()
