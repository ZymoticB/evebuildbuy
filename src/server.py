from tornado import ioloop
from tornado import web
from torndb import Connection
import json
import logging
import os.path

import settings

from item.item import ItemFactory

class BaseHandler(web.RequestHandler):
    def initialize(self, db):
        self.db = db

class ItemHandler(BaseHandler):
    def get(self, item):
        me = int(self.get_argument('me', 0))
        logging.info("item: %s me: %s", item, me)
        item = ItemFactory(self.db, item, me=me)
        item_dict = item.to_dict()
        self.write(json.dumps(item_dict, indent=4, sort_keys=True))

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    db = Connection('localhost', 'evedump', user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD)
    path = os.path.join(os.path.dirname(__file__), "static")
    logging.info("path: %s", path)
    routes = [
            (r"/static/(.*)", web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "static")}),
            (r"/item/(?P<item>[a-zA-Z0-9_]+)/?", ItemHandler, dict(db=db))
            ]
    application = web.Application(routes)
    application.listen(6969)
    ioloop.IOLoop.instance().start()
