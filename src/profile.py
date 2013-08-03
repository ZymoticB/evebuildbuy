if __name__ == "__main__":
    from item.item import ItemFactory
    from torndb import Connection
    import settings
    db = Connection('localhost', 'evedump', user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD)
    import cProfile
    cProfile.run("ItemFactory(db, 'archon', me=2, part_me=50).to_dict()")
