from tornado import ioloop
from tornado import web
from torndb import Connection
import json

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
    db = Connection('localhost', 'evedump', user='eve', password='4Td#xA3c.0)J;Ni_k$(E')
    application = web.Application([(r"/item/(?P<item>[a-zA-Z_]+)/?", ItemHandler, dict(db=db))])
    application.listen(6968)
    ioloop.IOLoop.instance().start()
