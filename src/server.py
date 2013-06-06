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
        item = ItemFactory(self.db, item)
        item_dict = item.to_dict()
        self.write(json.dumps(item_dict, indent=4))

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    db = Connection('localhost', 'evedump', user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD)
    application = web.Application([(r"/item/(?P<item>[a-zA-Z_]+)/?", ItemHandler, dict(db=db))])
    application.listen(6969)
    ioloop.IOLoop.instance().start()
