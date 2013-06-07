from tornado import ioloop
from tornado import web
from torndb import Connection
import json
import logging

import settings

from item.item import ItemFactory

class BaseHandler(web.RequestHandler):
    def initialize(self, db):
        self.db = db

class ItemHandler(BaseHandler):
    def get(self, item):
        me = int(self.get_argument('me', 0))
        cache = bool(self.get_argument('cache', True))
        part_me = int(self.get_argument('part_me', 0))
        logging.info("me: %s, cache: %s", me, cache)
        item = ItemFactory(self.db, item, me=me, cache=cache, part_me=me)
        item_dict = item.to_dict()
        self.write(json.dumps(item_dict, indent=4))

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    db = Connection('localhost', 'evedump', user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD)
    application = web.Application([(r"/item/(?P<item>[a-zA-Z_]+)/?", ItemHandler, dict(db=db))])
    application.listen(6969)
    ioloop.IOLoop.instance().start()
